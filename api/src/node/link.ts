/**
 * The link between the outlet and the cloud — and the one place it can be cut.
 *
 * WHY THERE IS EXACTLY ONE SEAM. GJ-10 requires the internet to be lost and the outlet to
 * carry on. A test that simulated an outage by stubbing four different modules would
 * prove that those four stubs work; the thing that has to be true is that NOTHING ELSE in
 * the node reaches the cloud. So every cloud call goes through this file, and cutting the
 * link is one boolean read in one place.
 *
 * That makes the claim checkable rather than asserted: if some other module opened a
 * socket to the cloud, an outage test would still pass while the outlet quietly depended
 * on a network that was supposed to be gone. tests/m5a asserts the shape of this — that
 * the node's source reaches the cloud here and nowhere else — for the same reason
 * tools/uncalled_routes.py counts call sites rather than trusting that they exist.
 *
 * WHAT "CUT" MEANS, STATED HONESTLY. EDGE_UPLINK=cut makes the client refuse to dial, the
 * way it would with the WAN down. It is not a severed cable and not a firewall rule: the
 * process is still running on a machine with a working network stack. What it faithfully
 * reproduces is the only thing the node can observe — that the cloud is unreachable — and
 * what it does not reproduce is a partial failure, a slow link or a DNS lie. Those are
 * M5b's problem and are recorded, not implied away.
 */

import { existsSync } from 'node:fs';

export type UplinkState = 'up' | 'cut';

export class CloudUnreachable extends Error {
  constructor(public readonly endpoint: string) {
    super(`CLOUD_UNREACHABLE: ${endpoint}`);
    this.name = 'CloudUnreachable';
  }
}

/**
 * Read every time rather than captured at construction: an outage starts mid-process.
 *
 * TWO WAYS TO CUT IT, AND THE SECOND IS THE ONE A PERSON CAN USE.
 *
 * EDGE_UPLINK=cut is what a test sets when it starts the worker. It cannot be changed
 * afterwards — a running process's environment is fixed — so cutting the link on a floor
 * that is already serving meant killing the worker and starting another, and killing a
 * named process is exactly the thing that quietly does not work here: `pkill -f
 * sync-worker` matched nothing on Windows and left three workers running, one of which
 * kept reporting the outlet connected while the "cut" one said otherwise.
 *
 * So there is also a FILE. If the path in EDGE_UPLINK_CUT_FILE exists, the link is cut;
 * delete it and it is back. An operator walking the floor touches a file and watches the
 * banner appear, with no process to find and no window to keep open. It is still one seam:
 * both forms are read here and nowhere else.
 */
export function uplinkState(source: NodeJS.ProcessEnv = process.env): UplinkState {
  if ((source.EDGE_UPLINK ?? 'up').trim().toLowerCase() === 'cut') return 'cut';
  const marker = (source.EDGE_UPLINK_CUT_FILE ?? '').trim();
  if (marker !== '' && existsSync(marker)) return 'cut';
  return 'up';
}

export interface CloudExchange {
  /** Events the outlet is offering, oldest first. */
  events: Array<{ eventId: string; sequence: string; subject: string; eventKind: string;
                  payload: unknown; occurredAt: string }>;
}

export interface CloudAcknowledgement {
  /** The event ids the cloud accepted. Anything absent stays pending and is offered again. */
  accepted: string[];
  /** The protocol version the cloud speaks, so FR-EDG-012 can refuse an incompatible peer. */
  protocolVersion: number;
  /**
   * FR-EDG-026. What the node needs in order to answer for a session the cloud started:
   * live sessions and the idempotency keys already spent against them.
   *
   * IT RIDES THE ACKNOWLEDGEMENT RATHER THAN A SECOND CALL. The node exchanges every round
   * while the link is up, and when the link is down there is nothing to fetch — a node in
   * an outage should already be holding what it needs, which is the entire point. A
   * separate endpoint would add a round trip that is only ever made at the moment it can
   * least be spared.
   *
   * Optional because a cloud that predates this field is a cloud that sends no continuity,
   * and the node applying nothing is the correct reading of that.
   */
  continuity?: Array<{ recordKind: 'session' | 'idempotency'; recordKey: string;
                       payload: unknown; validUntil: string }>;
}

export interface CloudLink {
  readonly endpoint: string;
  exchange(request: CloudExchange): Promise<CloudAcknowledgement>;
}

/**
 * The cloud as reached over HTTP.
 *
 * The cloud side of M5a is the same service running without a node profile, so this posts
 * to it. Every call checks the seam first — before DNS, before the socket — because a
 * process that resolves a name during an outage is a process with a five-second pause in
 * front of a waiter.
 */
export class HttpCloudLink implements CloudLink {
  constructor(public readonly endpoint: string,
              private readonly token: string,
              private readonly env: NodeJS.ProcessEnv = process.env) {}

  async exchange(request: CloudExchange): Promise<CloudAcknowledgement> {
    if (uplinkState(this.env) === 'cut') {
      throw new CloudUnreachable(this.endpoint);
    }
    const response = await fetch(`${this.endpoint}/x/v1/exchange`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${this.token}`,
      },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      throw new CloudUnreachable(`${this.endpoint} answered ${response.status}`);
    }
    return await response.json() as CloudAcknowledgement;
  }
}

/**
 * A cloud that accepts everything, for a node with nowhere to send.
 *
 * Used when EDGE_CLOUD_ENDPOINT is unset — a demonstration floor with no cloud beside it.
 * It is NOT a fallback for a failed call: a link that quietly succeeded when the real
 * cloud was unreachable would make an outage invisible, which is the one thing this whole
 * gate exists to make visible.
 */
export class LoopbackCloudLink implements CloudLink {
  readonly endpoint = 'loopback';

  constructor(private readonly env: NodeJS.ProcessEnv = process.env) {}

  async exchange(request: CloudExchange): Promise<CloudAcknowledgement> {
    if (uplinkState(this.env) === 'cut') {
      throw new CloudUnreachable(this.endpoint);
    }
    return {
      accepted: request.events.map((event) => event.eventId),
      protocolVersion: 1,
      // NO CONTINUITY, AND THAT IS THE TRUTHFUL ANSWER RATHER THAN A GAP. This link stands
      // in for a cloud that is not there; a cloud that is not there has no sessions of its
      // own to hand over, so there is nothing for a node to take up. Returning fabricated
      // records would make the node believe it had absorbed a handoff that never happened.
      continuity: [],
    };
  }
}

export function cloudLinkFrom(env: NodeJS.ProcessEnv = process.env): CloudLink {
  const endpoint = (env.EDGE_CLOUD_ENDPOINT ?? '').trim();
  if (endpoint === '') return new LoopbackCloudLink(env);
  return new HttpCloudLink(endpoint, env.EDGE_CLOUD_TOKEN ?? '', env);
}

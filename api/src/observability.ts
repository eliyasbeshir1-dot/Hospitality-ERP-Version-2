/**
 * Metrics and tracing behind a replaceable provider interface (FR-OPS-004).
 *
 * No vendor type reaches a caller. Swapping the provider is implementing this interface
 * and changing one line in server.ts; nothing in a route or a job changes.
 */
export interface Span {
  setAttribute(key: string, value: string | number | boolean): void;
  recordError(error: unknown): void;
  end(): void;
}

export interface ObservabilityProvider {
  readonly name: string;
  counter(name: string, value: number, labels?: Record<string, string>): void;
  histogram(name: string, value: number, labels?: Record<string, string>): void;
  startSpan(name: string, attributes?: Record<string, string>): Span;
  snapshot(): Record<string, number>;
}

/**
 * The provider used when none is configured. It records in memory so metrics are real and
 * inspectable in tests, and it is honest about being local: nothing is exported anywhere.
 */
export class InMemoryObservability implements ObservabilityProvider {
  readonly name = 'in-memory';
  private readonly counters = new Map<string, number>();
  private readonly histograms = new Map<string, number[]>();

  private key(name: string, labels?: Record<string, string>): string {
    if (!labels || Object.keys(labels).length === 0) return name;
    const flat = Object.keys(labels).sort().map((k) => `${k}=${labels[k]}`).join(',');
    return `${name}{${flat}}`;
  }

  counter(name: string, value: number, labels?: Record<string, string>): void {
    const k = this.key(name, labels);
    this.counters.set(k, (this.counters.get(k) ?? 0) + value);
  }

  histogram(name: string, value: number, labels?: Record<string, string>): void {
    const k = this.key(name, labels);
    const bucket = this.histograms.get(k) ?? [];
    bucket.push(value);
    this.histograms.set(k, bucket);
  }

  startSpan(name: string, attributes: Record<string, string> = {}): Span {
    const started = process.hrtime.bigint();
    const self = this;
    const attrs: Record<string, string> = { ...attributes };
    return {
      setAttribute(key, value) { attrs[key] = String(value); },
      recordError(error) { self.counter('span.error', 1, { span: name }); void error; },
      end() {
        const elapsedMs = Number(process.hrtime.bigint() - started) / 1_000_000;
        self.histogram('span.duration_ms', elapsedMs, { span: name });
      },
    };
  }

  snapshot(): Record<string, number> {
    const out: Record<string, number> = {};
    for (const [k, v] of this.counters) out[k] = v;
    for (const [k, values] of this.histograms) {
      out[`${k}.count`] = values.length;
      out[`${k}.sum`] = Number(values.reduce((a, b) => a + b, 0).toFixed(3));
    }
    return out;
  }
}

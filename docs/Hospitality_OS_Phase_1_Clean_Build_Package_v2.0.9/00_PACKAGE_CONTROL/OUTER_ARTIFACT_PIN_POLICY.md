# Outer Artifact Pin Policy - v2.0.9

The Package M0 review delivery is incomplete unless the generated ZIP and its
publisher-supplied `.zip.sha256` sidecar are attached together as two separate artifacts.
The reviewer must independently compute the ZIP SHA-256 before relying on either artifact.

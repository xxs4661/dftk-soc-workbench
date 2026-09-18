# Verification and preservation

The four new diagnostics and both same-map comparisons are complete. Current
public replay exits 0; strict optimization acceptance exits 1 because both
performance goals were missed. The numerical execution commit remains
`761e09d8fe99f99fcccb0f1b10704916d336ccb8`.

The new raw-run archive contains 271 files / 1,616,279,399 bytes. Every file's
source-before, copy-stream, source-after and archived SHA-256 agrees. A finite
actual restore checked 55 files / 534,338,793 bytes, including each task's
`map-001.bin` and source/environment/control text. Original files remain in place.

- Raw manifest SHA-256: `0765a9b4760dd3966c56a4800ced780ea700f1f97793301ce293b44c1ba296d6`.
- Restore manifest SHA-256: `cd62f1c2ecd857bf4daa7ae1dcc0b25773db466516559d7af31b6c014d96a7bd`.
- Scope: same-machine repository-external backup; byte integrity only, not verified resumability.
- No binary checkpoint was deserialized for archiving or restoration.

Final candidate-clone checks and the code/preparation-log archive supplement are
NOT_RUN at this intermediate publication commit. Their actual outcomes will be
recorded after execution, without rewriting the numerical execution or old evidence.

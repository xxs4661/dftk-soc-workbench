# Frozen source records

[sources.lock](sources.lock) records the original inspected dependencies, input
source and historical upstream observations. It is not a live upstream status
service. Existing records stay unchanged when a later case introduces a different
pseudopotential or executable; that case must record its own reviewed immutable
identity, source, SHA-256, licensing boundary and actual runtime evidence.

The workbench Project, Manifest and checksums remain frozen. Do not change source
locks or hashes to silence an identity failure. Do not store credentials, private
absolute paths, UPF payloads, caches or downloaded source trees here.

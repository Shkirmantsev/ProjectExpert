# Specification delta

Proposed; not adopted current behavior.

## ADDED Requirements

### Requirement: Java implementation evidence fallback
Java research SHALL prefer matching source JARs, retain public classfile evidence when source is absent, and permit a bounded optional decompiler for supported classfile versions. Decompiled bodies SHALL be labelled inferred reconstructions with binary hash, member and tool version. Missing tools SHALL NOT prevent metadata or signature inspection.

#### Scenario: Class-only dependency
- **GIVEN** a JAR without matching sources and an available supported decompiler
- **WHEN** a method body is requested
- **THEN** a bounded reconstructed body and its provenance are returned

#### Scenario: Decompiler absent
- **GIVEN** a class-only JAR without a supported decompiler
- **WHEN** inspection runs
- **THEN** signatures remain available and the unavailable body is reported explicitly

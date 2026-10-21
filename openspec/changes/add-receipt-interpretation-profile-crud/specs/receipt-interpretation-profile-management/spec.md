# Spec Delta

## Purpose

Permitir que usuarios gerenciem seus perfis privados de interpretacao e regras filhas de forma consistente, consultando os padroes compartilhados sem poder altera-los.

## ADDED Requirements

### Requirement: Authenticated aggregate endpoints
The API SHALL expose POST and GET /receipt-interpretation-profiles and GET, PUT and DELETE /receipt-interpretation-profiles/{profile_id}. Every endpoint SHALL require authentication. Children SHALL have no independent endpoints. Creation SHALL return 201 with the aggregate; reads 200; update and delete 200 with a message. Invalid credentials SHALL return 401 and malformed UUIDs 422.

#### Scenario: Create and inspect
- **WHEN** an authenticated user submits a valid private profile with child rules
- **THEN** the API returns 201 with generated identifiers and the complete persisted aggregate

#### Scenario: Authentication required
- **WHEN** any operation receives missing or invalid credentials
- **THEN** it returns 401 without accessing or changing profile data

### Requirement: Private ownership and shared read access
Reads SHALL expose only non-deleted profiles owned by the authenticated user and the non-deleted shared General profile. Mutations SHALL affect only owned private profiles. Ownership SHALL come exclusively from authentication. Missing, deleted or foreign profiles SHALL return 404. Updating or deleting General SHALL return 403. Public payloads SHALL reject ownership fields with 422.

#### Scenario: Read General without editing it
- **WHEN** a user reads the existing General profile and then attempts to update or delete it
- **THEN** reading succeeds and each mutation returns 403 without changes

#### Scenario: Foreign profile
- **WHEN** a user reads or mutates another user's profile
- **THEN** the result is 404 and foreign child identities are not disclosed

### Requirement: Private profile identity
Creation SHALL require a nonempty whitespace-normalized name and institution_code. Codes SHALL be trimmed, uppercased and match [A-Z0-9][A-Z0-9_-]{0,63}. Non-deleted private profiles SHALL have unique codes per owner, including inactive profiles; conflicts SHALL return 409, including concurrent writes. The code SHALL be immutable after creation.

#### Scenario: Normalized duplicate
- **WHEN** a user owning code NUBANK creates another profile with code " nubank "
- **THEN** the API returns 409; another owner can independently use NUBANK

#### Scenario: Code update forbidden
- **WHEN** an update supplies institution_code, even unchanged
- **THEN** the API returns 422 and preserves the aggregate

### Requirement: Complete profile representation
Responses SHALL include id, name, institution_code, scope (system or private), is_active, timestamps, identification_rules and field_rules, without user_id or child profile_id. Children SHALL include their IDs, configuration fields, status and timestamps. Reads SHALL include inactive non-deleted profiles and children, omit deleted children and use deterministic ordering.

#### Scenario: Inactive records remain inspectable
- **WHEN** an accessible inactive profile has inactive rules and deleted rules
- **THEN** the response includes the inactive records but excludes deleted rules

### Requirement: Typed field configurations
Field rules SHALL target only fields of ReceiptData and contain configuration with strategy regex, 1 to 10 ordered patterns and a supported parser. Each pattern SHALL be nonblank, at most 2000 characters, compile with case-insensitive matching and contain a named value group. Money fields SHALL use decimal_br, dates date_numeric_br or date_month_name_pt_br, and text fields text. Invalid configurations SHALL return 422.

#### Scenario: Valid Nubank date override
- **WHEN** payment_date uses a pattern with a named value group and date_month_name_pt_br
- **THEN** the configuration is accepted without executing it on a document

#### Scenario: Invalid converter or expression
- **WHEN** paid_amount uses parser text, a pattern is malformed, or its value group is absent
- **THEN** the API returns 422 without persisting any part of the aggregate

### Requirement: Identification and payload validation
Identification rules SHALL contain a nonblank compilable regex of at most 2000 characters and a strict positive integer weight. Creation SHALL default child lists to empty and is_active to true. Unknown fields, managed IDs/timestamps, null required fields and null lists SHALL return 422. Each list SHALL contain at most 100 entries. General SHALL NOT receive identification rules through this API.

#### Scenario: Invalid identification rule
- **WHEN** a rule has invalid syntax, blank pattern or weight true, zero or negative
- **THEN** creation or update returns 422 without changes

#### Scenario: Managed fields and list limits
- **WHEN** creation supplies a child ID, user_id, a null list or more than 100 entries in a list
- **THEN** the API returns 422

### Requirement: Reconciliation update semantics
PUT SHALL preserve omitted root fields and child lists. Supplied lists SHALL replace their live membership: update IDs in that collection, create entries omitting ID and logically delete absent entries. An empty list SHALL remove all live entries. Retained entries SHALL require their full editable fields, with is_active defaulting to true. Explicit null IDs, duplicate IDs or IDs outside the target live collection SHALL return 422.

#### Scenario: Independent collection update
- **WHEN** an update supplies field_rules but omits identification_rules and name
- **THEN** only field_rules is reconciled and omitted values remain unchanged

#### Scenario: Mixed child reconciliation
- **WHEN** a list retains modified A, omits B and introduces C without ID
- **THEN** A retains its ID, B is logically deleted and C receives a new ID

#### Scenario: Invalid child identity
- **WHEN** a supplied ID belongs to another profile, the other child collection or a deleted rule
- **THEN** the API returns 422 without moving or restoring any rule

### Requirement: Unique final field membership
Final non-deleted field rules SHALL be unique by field_name within a profile, including inactive rules. Duplicate final fields SHALL return 422. Renaming or replacing rules SHALL be validated against the final list, allowing name swaps and reuse of a removed field in the same update.

#### Scenario: Swap field names
- **WHEN** two retained text rules exchange field names with compatible parsers
- **THEN** the update succeeds without transient uniqueness conflicts

#### Scenario: Duplicate final field
- **WHEN** two entries target payment_date and one is inactive
- **THEN** the update returns 422 and neither entry is changed

### Requirement: Atomic lifecycle and concurrent changes
Each mutation SHALL commit profile and child changes together or roll back all of them. Concurrent mutations of one profile SHALL be serialized and revalidated. DELETE SHALL logically delete and deactivate the root and live children, preserving prior deletion timestamps. Repeated deletion SHALL return 404. Infrastructure errors SHALL surface as errors, not success or empty results.

#### Scenario: Failure during persistence
- **WHEN** saving a child or committing fails after a root change
- **THEN** no part of the mutation remains committed

#### Scenario: Concurrent stale child update
- **WHEN** a concurrent update references a child removed by an earlier committed mutation
- **THEN** revalidation returns 422 rather than restoring the child

### Requirement: Filtered root pagination
Listing SHALL support name, institution_code and scope filters using AND semantics. It SHALL return an array without page/offset or the existing pagination envelope when either is supplied. Pagination SHALL count profiles, not child rows. Missing General SHALL NOT trigger automatic creation, and empty results SHALL remain empty.

#### Scenario: Combined visible profiles
- **WHEN** a user lists without scope filtering
- **THEN** results contain their private profiles and existing General, never another user's profiles

#### Scenario: Page with children
- **WHEN** a page contains profiles with multiple child rules
- **THEN** totals and limits count only profiles and every returned profile contains both child lists

### Requirement: Configuration management only
The delivery SHALL NOT execute configured regex against receipt text, resolve inherited rules, change upload behavior, seed General or provide administrative mutations, simulation or version history. Profile management SHALL remain within the receipt domain, preserving existing table names and records.

#### Scenario: Save rules without changing receipt processing
- **WHEN** a user creates or updates a profile
- **THEN** it is persisted for future integration while existing fixed interpretation behavior remains unchanged

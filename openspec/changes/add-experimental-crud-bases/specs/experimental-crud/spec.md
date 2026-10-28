# Spec Delta

## Purpose

Oferecer um contrato CRUD interno reutilizavel para experimentacao arquitetural, sem migrar os dominios ativos nem alterar o comportamento publico da API.

## ADDED Requirements

### Requirement: Isolated experimental package
The experimental CRUD API SHALL be available separately from the active application. Existing routes, domain services, repositories and database schemas SHALL remain unchanged and SHALL NOT depend on the experimental package.

#### Scenario: Existing application remains independent
- **WHEN** the active application starts without importing the experimental package
- **THEN** its registered operations and dependency wiring remain unchanged

### Requirement: Reusable complete CRUD
Consumers SHALL obtain listing, lookup, creation, partial update and deletion through a shared flow, supplying resource metadata and domain-specific extensions without reimplementing that flow. Creation SHALL return the entity; update and deletion SHALL return the existing message-shaped result.

#### Scenario: Simple resource
- **WHEN** a resource supplies its persistence mapping, input schemas and entity construction
- **THEN** it can perform all five operations without defining its own listing, lookup, update or deletion orchestration

#### Scenario: Lookup absence
- **WHEN** lookup finds no accessible record
- **THEN** required lookup, update and deletion report 404, while explicitly optional lookup returns null without hiding persistence errors

### Requirement: Mandatory owner scope
Every default CRUD operation SHALL require a trusted owner identifier independently of client filters or payloads. Client data SHALL NOT replace ownership or server-managed identity and timestamps. Missing owner scope SHALL fail before querying or mutating data.

#### Scenario: Foreign resource
- **WHEN** one owner looks up, updates or deletes a record belonging to another owner
- **THEN** the record is treated as absent and neither owner's data is changed

#### Scenario: Forged ownership
- **WHEN** filters or payloads attempt to supply a different owner or managed fields
- **THEN** trusted ownership is preserved and managed fields are not applied from client data

#### Scenario: Unscoped repository call
- **WHEN** a default repository operation is invoked without a valid owner scope
- **THEN** it reports an explicit input error and performs no database operation

### Requirement: Compatible listing and pagination
Listings SHALL return a list without pagination or the existing custom pagination envelope when pagination is requested. Items and totals SHALL use the same owner, visibility and resource filters. Caller filters SHALL NOT be mutated, and unsupported filters or sorting SHALL produce an explicit error.

#### Scenario: Filtered pagination
- **WHEN** an owner requests a filtered page in a dataset containing multiple owners
- **THEN** both items and total reflect only accessible matching root entities, not joined child rows

#### Scenario: Valid empty result
- **WHEN** a successful listing has no matching entities
- **THEN** it returns an empty list or an envelope with zero items and total zero

#### Scenario: Invalid filter
- **WHEN** a caller supplies an unsupported filter or ordering field
- **THEN** the operation fails explicitly rather than silently broadening the query

### Requirement: Safe partial updates
Updates SHALL preserve omitted fields, apply explicit null only as permitted by the input schema, and update existing accessible entities only. Domain extensions SHALL be able to validate and transform input before persistence without duplicating the shared CRUD flow.

#### Scenario: Omitted and cleared fields
- **WHEN** an update omits a name but explicitly clears a nullable description
- **THEN** the previous name remains unchanged and the description becomes null

#### Scenario: Normalized uniqueness
- **WHEN** a resource extension derives a normalized name and detects a duplicate for the owner
- **THEN** creation or update reports 409 before persistence, while a self-update is allowed

#### Scenario: No implicit upsert
- **WHEN** update targets an inaccessible or unknown identifier
- **THEN** it reports 404 and creates no record

### Requirement: Explicit deletion behavior
Default deletion SHALL physically remove the accessible entity. A resource extension SHALL be able to replace deletion and read visibility with logical deletion behavior without changing the shared service flow. Logical deletion SHALL NOT be inferred solely from the presence of a deletion timestamp.

#### Scenario: Physical deletion
- **WHEN** an owner deletes a default resource
- **THEN** its row is removed only after the mutation commits successfully

#### Scenario: Logical deletion extension
- **WHEN** a resource configures logical deletion and corresponding visibility
- **THEN** deletion preserves its row, subsequent normal reads exclude it and repeated deletion reports 404

### Requirement: Atomic mutation boundary
Each default mutation SHALL commit once after validation and persistence complete and SHALL roll back on validation, write or commit failure. Persistence primitives SHALL NOT commit independently. Nested experimental transaction boundaries SHALL fail explicitly, and rollback failure SHALL be logged without replacing the original failure.

#### Scenario: Composed persistence
- **WHEN** a mutation extension writes two entities and the second write fails
- **THEN** neither change is committed and no success result is returned

#### Scenario: Commit failure
- **WHEN** persistence succeeds but commit fails
- **THEN** rollback is attempted, the original failure is reported and post-commit actions do not run

#### Scenario: Previously started read transaction
- **WHEN** an exclusive request session has already started a transaction through a read
- **THEN** the mutation boundary can complete that transaction without intermediate commits

### Requirement: Explicit observability and errors
CRUD failures SHALL use the existing service error translation and contextual logging. Database errors SHALL NOT become empty results or null lookups. Success SHALL be logged only after successful completion, including commit for mutations.

#### Scenario: Failed listing
- **WHEN** listing encounters a persistence failure
- **THEN** it reports an error with operation and requester context and emits no CRUD success log

#### Scenario: Failed optional lookup
- **WHEN** an optional lookup encounters a database failure
- **THEN** it reports the failure instead of returning null

### Requirement: Reusable operation context
Consumers SHALL be able to wrap both inherited CRUD and specialized service operations in the same asynchronous operation context. It SHALL translate exceptions and log success only on normal completion, preserving operation, requester and optional target context. A public call SHALL NOT duplicate service success logs or error translation through internal composition.

#### Scenario: Specialized operation uses shared context
- **WHEN** a consumer performs a specialized operation through the shared context without using generic CRUD
- **THEN** it receives the same contextual error handling and completion-only success logging as inherited CRUD

#### Scenario: Cached lookup fails during database access
- **WHEN** a cache miss leads to a database failure inside one public service call
- **THEN** service error translation occurs once and no service success is logged

### Requirement: Optional cache-aside reads
Consumers SHALL have reusable cached listing and individual lookup with configurable namespace, response schema and TTL. A hit SHALL avoid database access; a miss SHALL fetch, validate and cache successful results. Cached and freshly fetched results SHALL use the same schema and list or custom pagination envelope. Plain CRUD SHALL remain usable without cache.

#### Scenario: Cache hit and miss
- **WHEN** a configured cached read is performed twice with identical criteria
- **THEN** the first miss fetches and caches validated data and the next hit returns the same response shape without querying the database

#### Scenario: Empty list hit
- **WHEN** a valid empty list is cached
- **THEN** it is returned as a hit rather than triggering another database query

#### Scenario: Failed read is not cached
- **WHEN** a database lookup fails or reports an absent individual resource
- **THEN** no success-shaped value or negative entry is written to cache

### Requirement: Owner-scoped cache identity and refresh
Cache keys SHALL distinguish trusted owners and all effective query criteria, including pagination, ordering and case-sensitive lookup values. Explicit refresh SHALL invalidate the applicable scope and repopulate from the database without mutating caller inputs. Cache refresh controls SHALL NOT affect query identity.

#### Scenario: Different owners and criteria
- **WHEN** cached reads differ by owner, pagination, filter, ordering or case-sensitive lookup value
- **THEN** they do not reuse each other's cache entries

#### Scenario: Explicit refresh
- **WHEN** a caller requests a forced cache refresh
- **THEN** the applicable owner-scoped cache is invalidated before fetching fresh data and caller filters remain unchanged

### Requirement: Built-in post-commit cache invalidation
CRUD SHALL work without a cache dependency. When cache is configured, shared invalidation SHALL clear the resource's owner-scoped entries and configured parent scopes after successful creation, update and deletion, never after rollback. Consumers SHALL NOT need to implement ordinary invalidation. Failure SHALL be logged as a warning without concealing a committed result.

#### Scenario: Cache disabled
- **WHEN** a consumer does not configure cache
- **THEN** CRUD performs no cache access or cache initialization

#### Scenario: Successful mutation invalidates cache
- **WHEN** a configured mutation commits
- **THEN** shared invalidation clears the resource and configured parent scopes for the trusted owner, including cached aliases and lists

#### Scenario: Cache unavailable after commit
- **WHEN** post-commit invalidation raises an infrastructure error
- **THEN** a contextual warning records the failure and the committed mutation result is returned

### Requirement: Domain-specific behavior remains explicit
The experimental CRUD contract SHALL allow resource-specific query, validation, persistence and deletion extensions. It SHALL NOT implicitly implement aggregate reconciliation, shared-system visibility, authentication, receipt interpretation or financial summaries.

#### Scenario: Specialized resource
- **WHEN** a resource needs aggregate reconciliation or shared-system visibility
- **THEN** it supplies an explicit specialized extension or retains its existing implementation rather than inheriting assumed generic business rules

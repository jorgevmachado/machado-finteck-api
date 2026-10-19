# category-management Specification

## Purpose

Permitir que cada usuario gerencie categorias e suas subcategorias como uma unidade consistente, com acesso isolado, ordenacao previsivel e exclusao logica sem persistencia parcial.

## Requirements

### Requirement: Category endpoints
The category API SHALL expose six operations: create via POST /categories, update via PUT /categories/{category_id}, list via GET /categories, get via GET /categories/{category_id}, delete via DELETE /categories/{category_id} and seed via POST /categories/seed. Subcategories SHALL NOT have independent endpoints.

#### Scenario: Available category operations
- **WHEN** a client inspects the category API contract
- **THEN** exactly those six method/path combinations are available, with no subcategory operations

### Requirement: Authenticated owner access
The system SHALL require valid authentication on every category endpoint and derive ownership exclusively from the authenticated user. Unknown categories, deleted categories and categories owned by another user SHALL return 404 on individual reads and mutations.

#### Scenario: Missing or invalid credentials
- **WHEN** an unauthenticated request or a request with an invalid or expired token accesses any category endpoint
- **THEN** the response is 401 and no category operation is performed

#### Scenario: Another user's category
- **WHEN** a user attempts to get, update or delete another user's category
- **THEN** the response is 404 and neither aggregate changes

#### Scenario: Client attempts to supply ownership
- **WHEN** a payload includes user_id or a nested category_id
- **THEN** the response is 422 and the supplied ownership is never used

### Requirement: Category and subcategory data
The system SHALL represent a category with id, name, icon, color, is_active, timestamps and subcategories. Each child SHALL contain id, name, icon, color, is_active, order and timestamps. Identifiers SHALL be server-generated UUIDs. Ownership and internal persistence fields SHALL NOT appear in public responses.

#### Scenario: Created aggregate representation
- **WHEN** a valid category with two new subcategories is created
- **THEN** the response contains distinct UUIDs, created_at timestamps, nullable updated_at and deleted_at, and the nested children, without user_id, category_id or internal comparison fields

### Requirement: Input validation
The system SHALL collapse whitespace and trim names, rejecting empty names. Optional colors SHALL match #RRGGBB with case-insensitive hex digits. Order SHALL be a strict positive integer, allowing gaps. Unknown fields, root IDs, creation child IDs and managed timestamps in payloads SHALL be rejected with 422. Only reconciliation SHALL accept IDs to identify existing children.

#### Scenario: Name normalization
- **WHEN** a name contains leading, trailing or repeated whitespace
- **THEN** the stored and returned name is trimmed with internal whitespace collapsed

#### Scenario: Invalid scalar values
- **WHEN** a name is whitespace-only, a color is #FFF or lacks #, or order is zero, negative, boolean, fractional or a numeric string
- **THEN** the response is 422 and no changes are persisted

#### Scenario: Valid visual metadata and order gaps
- **WHEN** icon is null, color is #aB123F and child orders are 1 and 5
- **THEN** those values are accepted

#### Scenario: Server-managed fields in creation
- **WHEN** creation includes an id at either level, created_at, updated_at or deleted_at
- **THEN** the response is 422

### Requirement: Unique category names per owner
The system SHALL enforce unique whitespace-normalized category names per user among non-deleted categories, including inactive categories, on create and update. Comparison SHALL be case-sensitive and preserve accents and punctuation. Conflicts SHALL return 409, including concurrent requests. Different users SHALL be allowed the same name.

#### Scenario: Equivalent whitespace
- **WHEN** a user with category "Casa principal" creates " Casa   principal "
- **THEN** the response is 409

#### Scenario: Rename collision and self-update
- **WHEN** a user renames a category to another non-deleted category's name
- **THEN** the response is 409, while keeping its own normalized name is allowed

#### Scenario: Inactive and deleted categories
- **WHEN** a name belongs to an inactive non-deleted category
- **THEN** it remains reserved, but becomes reusable after that category is logically deleted

#### Scenario: Different owners and different spelling
- **WHEN** two users create the same name, or one user creates "Casa" and "casa"
- **THEN** the requests are allowed independently

#### Scenario: Concurrent duplicate creation
- **WHEN** two requests for the same user concurrently create the same normalized name
- **THEN** exactly one succeeds and the other returns 409 without a partial aggregate

### Requirement: Category creation
POST /categories SHALL return 201 with the complete category and ordered children. Name SHALL be required; icon and color SHALL default to null and is_active to true at both levels. Subcategories SHALL default to an empty list when omitted. Explicit null SHALL be invalid for name, is_active, order and subcategories.

#### Scenario: Minimal category
- **WHEN** a user posts only a valid name
- **THEN** the response is 201 with is_active true, icon and color null and subcategories []

#### Scenario: Explicit inactive status
- **WHEN** creation supplies is_active false on the category or a child
- **THEN** the supplied false is preserved

#### Scenario: Null instead of a default
- **WHEN** creation supplies is_active null or subcategories null
- **THEN** the response is 422 rather than silently applying a default

### Requirement: Child order and identity consistency
The system SHALL require unique orders among all non-deleted children of a category, including inactive children. Reconciliation SHALL reject duplicate IDs, duplicate orders and IDs not belonging to a non-deleted child of the target category with 422. No child SHALL be transferred or implicitly restored.

#### Scenario: Duplicate order includes inactive child
- **WHEN** two supplied children have order 1 and one is inactive
- **THEN** the response is 422 and the aggregate is unchanged

#### Scenario: Invalid child identity
- **WHEN** an update repeats an ID or includes an unknown, deleted or another category's child ID
- **THEN** the response is 422 and no child is created, moved or restored

#### Scenario: Same order in different categories
- **WHEN** two categories each contain a child with order 1
- **THEN** both aggregates are valid

### Requirement: Complete child reconciliation
When subcategories is supplied, PUT /categories/{category_id} SHALL reconcile the complete list: update children identified by UUID, create children without id and logically delete absent children. Each entry SHALL require name and order; omitted icon/color SHALL default to null and is_active to true. Omitting subcategories SHALL preserve all children; explicit null SHALL return 422.

#### Scenario: Mixed reconciliation
- **WHEN** the persisted list is [A, B] and the update supplies modified A and new C without id
- **THEN** A retains its UUID with updated data, C receives a UUID, and B receives deleted_at and is_active false

#### Scenario: Empty list
- **WHEN** an update supplies subcategories []
- **THEN** all previously non-deleted children are logically deleted

#### Scenario: Missing list
- **WHEN** an update changes only the category name and omits subcategories
- **THEN** the response is 200, the name changes and every child's ID, attributes, order, status and timestamps remain unchanged

#### Scenario: Null child list
- **WHEN** an update supplies subcategories null
- **THEN** the response is 422 and neither the root nor any child changes

#### Scenario: Explicit null child identifier
- **WHEN** a new child is supplied with id null instead of omitting id
- **THEN** the response is 422

### Requirement: Root update semantics
PUT /categories/{category_id} SHALL update an existing category only and return 200 with a message string. Omitted root name, icon, color and is_active SHALL remain unchanged; explicit null SHALL clear icon or color but be invalid for name or is_active. The root ID SHALL come exclusively from the path and invalid UUIDs SHALL return 422.

#### Scenario: Root fields omitted or cleared
- **WHEN** an update includes subcategories and icon null but omits name, color and is_active
- **THEN** only icon and the child list change, and the response contains message

#### Scenario: Unknown category is not an upsert
- **WHEN** an update targets an unknown valid UUID
- **THEN** the response is 404 and no category is created

### Requirement: Owner-scoped ordered listing
GET /categories SHALL return 200 with only the authenticated user's non-deleted categories, including inactive ones. Every result SHALL include only non-deleted children ordered by ascending order, including inactive children. Listing SHALL support name filtering and the existing optional pagination envelope; without page or offset it SHALL return a list.

#### Scenario: Isolation and sorted children
- **WHEN** a user lists categories containing children with stored orders 5, 1 and a deleted child with order 2
- **THEN** only that user's non-deleted categories appear with child orders [1, 5]

#### Scenario: Inactive records remain visible
- **WHEN** a category and one of its children are inactive but not deleted
- **THEN** both remain visible with is_active false

#### Scenario: Pagination counts categories
- **WHEN** a user requests a page or offset with a limit and optional name filter
- **THEN** the existing pagination envelope counts and pages categories rather than joined child rows

#### Scenario: Empty results
- **WHEN** no category matches the authenticated owner and filters
- **THEN** the response is an empty list or an empty pagination envelope, not an error or another user's records

### Requirement: Owner-scoped individual category read
GET /categories/{category_id} SHALL return 200 with one non-deleted category owned by the authenticated user and its non-deleted children ordered by ascending order. Inactive records SHALL remain visible. Missing, deleted or inaccessible categories SHALL return 404; invalid UUIDs SHALL return 422.

#### Scenario: Read complete aggregate
- **WHEN** the owner requests an existing category by UUID with child orders 5 and 1 and an excluded child
- **THEN** the response contains that category and children ordered [1, 5], without the excluded child or ownership fields

#### Scenario: Inactive aggregate is readable
- **WHEN** the owner requests an inactive but non-deleted category with an inactive non-deleted child
- **THEN** the response is 200 and both records retain is_active false

#### Scenario: Missing or deleted aggregate
- **WHEN** an individual read targets an unknown or logically deleted category UUID
- **THEN** the response is 404 without exposing the historical aggregate

#### Scenario: Invalid identifier
- **WHEN** an individual read supplies an invalid UUID
- **THEN** the response is 422

### Requirement: Logical deletion of the aggregate
DELETE /categories/{category_id} SHALL atomically set deleted_at and is_active false on the root and all non-deleted children and return 200 with a message string. Previously deleted children SHALL retain their original deletion timestamp. Repeated deletion SHALL return 404 and SHALL NOT restore anything.

#### Scenario: Delete category and remaining children
- **WHEN** a user deletes their non-deleted category
- **THEN** the root and remaining children receive the same deletion timestamp and is_active false and disappear from normal reads

#### Scenario: Preserve prior deletion
- **WHEN** the deleted category includes a child removed by an earlier reconciliation
- **THEN** the child's original deleted_at is preserved

#### Scenario: Repeated deletion
- **WHEN** deletion is requested again for an already deleted category
- **THEN** the response is 404 and timestamps are unchanged

### Requirement: Atomic aggregate persistence
Every mutation SHALL persist the root and all child changes as one transaction. Validation, identity or persistence failure SHALL leave the previously committed aggregate unchanged. Infrastructure failures SHALL surface as errors rather than success or empty results.

#### Scenario: Failure while saving children
- **WHEN** a persistence failure occurs after a root change and one child change have been written but before completion
- **THEN** neither the root nor any child change is committed

#### Scenario: Failure during logical deletion
- **WHEN** deletion fails after changing the root but before all children are changed
- **THEN** the original root and children remain visible and unchanged

### Requirement: Safe reordering and concurrent mutations
The system SHALL validate the final child list rather than reject valid order swaps due to intermediate states. Concurrent updates and deletions of the same category SHALL be serialized and revalidated against the current committed aggregate; every committed result SHALL satisfy all aggregate invariants.

#### Scenario: Swap existing child positions
- **WHEN** two retained children change orders from [1, 2] to [2, 1]
- **THEN** the update succeeds without a transient uniqueness conflict

#### Scenario: Reuse removed order
- **WHEN** a child with order 1 is omitted and a new child receives order 1 in the same update
- **THEN** the old child is logically deleted and the new child is persisted at order 1

#### Scenario: Concurrent updates disagree about child membership
- **WHEN** two updates overlap and the first deletes a child referenced by the second
- **THEN** the second is revalidated after the first commits and returns 422 without restoring that child

### Requirement: Development example data
The development seed SHALL add at least five example categories, each with at least two children numbered sequentially from 1, to the existing user usuario@formacao.dev. Repeated execution SHALL not duplicate or overwrite existing user data. A missing user SHALL cause a clear failure without creating credentials.

#### Scenario: First and repeated execution
- **WHEN** the example user exists and the seed executes twice
- **THEN** the examples exist once and existing categories and children are unchanged

#### Scenario: Missing user
- **WHEN** the example user does not exist
- **THEN** execution stops with an explicit error before inserting categories or creating a user

### Requirement: Authenticated default category seed
POST /categories/seed SHALL require authentication, take no input payload and seed only the authenticated owner. The response SHALL be 200 with created and skipped counts. Existing non-deleted categories SHALL be skipped without modification. All missing aggregates SHALL be persisted in one transaction.

#### Scenario: Seed all defaults
- **WHEN** an authenticated user without defaults invokes the seed
- **THEN** created is 14 and skipped is 0 and all 59 children belong to that user's new categories

#### Scenario: Preserve existing aggregates and repeat safely
- **WHEN** a default category already exists for the owner, including an inactive category, and the seed is invoked repeatedly
- **THEN** the existing category and its children remain unchanged and each missing category is created only once

#### Scenario: Owner isolation
- **WHEN** another user already owns the default categories
- **THEN** those records do not prevent the authenticated user from receiving their own defaults

#### Scenario: Seed failure rolls back entire batch
- **WHEN** a write or commit fails after some defaults have been flushed
- **THEN** none of the new defaults are committed and the response is an error; concurrent name conflicts return 409

### Requirement: Default category catalog and icons
The catalog SHALL contain the requested 14 categories and 59 children with their supplied names, colors and sequential orders. Existing equivalent package icon keys SHALL be reused; missing icons SHALL use react-<component> references to documented react-icons/fa6 exports.

#### Scenario: Existing and missing package icons
- **WHEN** the default catalog is loaded
- **THEN** existing substitutes such as home and bolt are reused and missing icons such as FaBuilding are stored as react-FaBuilding, with their import source documented without modifying the frontend

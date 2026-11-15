# Image Editing

## Requirements

### Capability: Provider-backed editing tasks

- The seller can create an edit task from one owned image asset
- Supported operations are inpaint, outpaint, remove_object and upscale
- Every task stores operation, source asset, optional mask asset, target ratio and
  prompt parameters
- Cross-user source or mask assets return 404

### Capability: Explicit provider degradation

- If no edit provider is configured, the API returns a seller-readable error
- An edit task never falls back to unconstrained text-to-image
- Upscale can use a local Pillow path when AI edit models are unavailable

### Capability: Durable task execution

- Edit tasks use the existing durable image queue
- Credits are charged only after a successful output
- Output images are materialized into the normal image asset library

## Acceptance

- Edit request creates a pending task with operation metadata
- Local upscale produces a larger WebP/PNG asset without provider credentials
- Inpaint/outpaint/remove_object require an explicit provider and expose missing
  configuration
- Existing marketing-suite and reference-image behavior remains unchanged

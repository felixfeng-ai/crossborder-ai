# Marketing Image Suite

## Requirements

### Capability: Multi-platform suite creation

- Given an owned marketing campaign and 1-4 owned product reference assets
- When the seller selects at least two supported platforms and confirms generation
- Then the system creates one suite and one durable image task per platform
- And every task keeps the campaign, product references, platform preset and
  aspect ratio
- And the suite reports pending, processing, completed or partial_failed without
  hiding failed platform items

### Capability: Billing and idempotency

- Suite credit cost equals the sum of all platform task costs
- Insufficient credits reject the whole suite before any task is created
- Retrying the same user idempotency key returns the existing suite
- A failed platform task does not add a failure state to successful tasks

### Capability: Campaign asset compatibility

- Existing campaign asset cards continue to render individual variants
- Suite variants expose suite_id and platform metadata
- Cross-user campaign or reference assets return 404

## Acceptance

- Amazon, TikTok Shop and Shopify can be generated in one request
- Each platform creates one pending `ImageGenerationTask`
- Campaign assets return the same variants with platform labels
- Desktop and mobile suite controls have no horizontal overflow

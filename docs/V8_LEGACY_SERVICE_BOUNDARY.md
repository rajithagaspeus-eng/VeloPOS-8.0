# V8 preview legacy-service isolation contract

The 17 protected actions are covered by the PreviewTransactionGate, the persisted-session policy map and PreviewTransactionGateway. This includes sale/return/purchase, voids, payments, shifts, cash movements, expenses, stock adjustment/count, batch receipt and receipt printing. The preview gateway denies every action.

The architecture regression scans velopos_qt Python modules and rejects imports or calls to legacy financial mutation methods. This prevents a new Qt screen from bypassing the V8 preview gateway and reaching V7 service functions directly.

This guard protects the nontransactional preview boundary. It does not secure existing V7 services for commercial V8 use and is not a production authorization or idempotency service. Before any commercial transaction can be enabled, the original service transaction ownership, authenticated actor, branch, shift, license and persistent idempotency must be refactored and reviewed together. Existing V7 service behavior and data remain unchanged by this batch.

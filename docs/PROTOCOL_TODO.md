# Protocol / gameplay work remaining

Original-client `/web/ClientService/Login` and `/web/ClientService/Process`, compressed/XOR wire framing and a limited startup path are **now implemented** in the NEW backend. Historical 2.11 code is not imported or executed. Refer to `ORIGINAL_CLIENT_PROTOCOL.md` for verified local traces, and `ORIGINAL_OPERATION_COVERAGE.md` for the uncovered operation inventory.

The original Android client has **not** passed a real Windows/BlueStacks login → gameplay action → save → restart → reload acceptance test. Required next tasks:

1. Implement the remaining game operations and original response contracts, prioritising actual captured client calls.
2. Implement realistic background building production, quests, needs, full Riverside/Mountain and social/family rules from recoverable original data; avoid invented silent success responses.
3. Complete read-only original resource parity using locally supplied XAPK, OBB and authored inventory.
4. Integrate verified selected-instance setup, local XAPK patching/signing and targeted ADB installation in the future first-run wizard.
5. Verify Wi-Fi-on guest egress restrictions without disrupting host internet.
6. Test real save migration and independent villages in the actual original APK.

**No final installer should be built or distributed until the acceptance conditions above are met.**

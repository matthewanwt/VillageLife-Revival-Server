# Optional gem-priced Mega Spin backend proposal

This source proposal adds an opt-in purchase for the authored Mega wheel at a
proposed price of 20 gems. Existing launchers leave it disabled. An embedding
application can explicitly construct `OriginalClientGame` with
`enable_gem_mega_spin=True` to evaluate it.

After showing and confirming the price, an adapter submits the authenticated
`ClientFortune/GetGemMegaSpinResult` service with `intentId` (32 lowercase hex
characters, generated once per confirmed purchase) and `confirmedGemCost: 20`.
Cancel sends no purchase. Keep the same intent across transport retries and
restarts until its result is reconciled. A new intent is a new purchase. The
server rejects other prices and uses the existing insufficient-gems response.

Gem debit, saved RNG, reward and intent result commit in the existing repository
transaction. Retrying the same intent with a new RPC ID returns the original
result. The result contains the committed inventory and wheel model. A client
must avoid crediting the prize again when animating its reveal. Daily wheel
timers, streaks and the existing daily-spin service retain their current path.

The 20-gem price is a custom feature choice from a private prototype. It needs
maintainer review as product policy. It is independent of merged gem validation
PR #5 and collection PR #6. It does not represent a platform-store transaction.

Four synthetic engine tests exercise authenticated dispatch, disabled behavior,
confirmation validation, insufficient funds, rollback after a failed draw, and
purchase-intent replay after reopening the database in a new engine session.
Fixtures contain no original game tables, binaries, signing keys or player saves.
Earlier private native-client experiments informed the request/result design,
but this rebased upstream proposal has backend validation only. Native entry,
confirmation/reward presentation and platform acceptance remain pending. No
launcher flag, Android patch or native library is included in this proposal.

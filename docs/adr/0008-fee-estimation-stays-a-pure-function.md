# Fee estimation stays a pure function, not a FeeSource port

`pricing.fee_per_night(on_date)` is a pure seasonal estimate — peak vs shoulder rate keyed off the date, using BC Parks' published 2026 rates. It is deliberately NOT a `FeeSource` Protocol with an adapter, even though every other external data source in the codebase (`BCParksApi`, `Telegram`, the repos) is a port.

Reason: the BC Parks GoingToCamp API exposes no working pricing endpoint — every probed path returns 404. There is exactly one fee source today (the seasonal computation) and the second one is unknown; it may require reverse-engineering booking-flow XHRs. A Protocol now would be a hypothetical seam wrapping a single implementation — interface ceremony, and a lie about where the data comes from (it is computed, not fetched). When a real pricing endpoint is found, that is the moment to introduce `FeeSource`: two implementations is a real seam. Until then, a pure function is the honest shape.

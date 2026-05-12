# Example — basic chain-ladder run

> Once the MCP is wired into Claude Desktop (see the README), try this
> conversation.

**Me:**
> Run a chain ladder on this triangle and tell me the IBNR.
>
> ```
> AY 1: 1000, 1855, 2423, 2988, 3335, 3483, 3552, 3603, 3624, 3631
> AY 2: 1113, 2103, 2774, 3422, 3844, 4010, 4090, 4148, 4172, ?
> AY 3: 1265, 2433, 3233, 3977, 4458, 4658, 4751, 4818, ?,    ?
> AY 4: 1490, 2873, 3880, 4598, 5152, 5400, 5508, ?,    ?,    ?
> AY 5: 1725, 3261, 4351, 5323, 5969, 6249, ?,    ?,    ?,    ?
> AY 6: 1889, 3576, 4778, 5675, 6362, ?,    ?,    ?,    ?,    ?
> AY 7: 2061, 3833, 5066, 6020, ?,    ?,    ?,    ?,    ?,    ?
> AY 8: 2255, 4146, 5552, ?,    ?,    ?,    ?,    ?,    ?,    ?
> AY 9: 2415, 4506, ?,    ?,    ?,    ?,    ?,    ?,    ?,    ?
> AY 10: 2640, ?,    ?,    ?,    ?,    ?,    ?,    ?,    ?,    ?
> ```

**Claude** *(calls `compute_chain_ladder` and summarises)*:
> Using volume-weighted age-to-age factors, the chain ladder projects:
>
> | Total | Value |
> |---|---:|
> | Paid to date | 49,458 |
> | Ultimate | 65,883.37 |
> | **IBNR** | **16,425.37** |
>
> Selected factors trend from 1.879 at the front of the triangle down
> to 1.002 at the tail; the cumulative factor for the most recent AY
> (AY 10) is 3.69, so its ultimate ≈ 2,640 × 3.69 ≈ 9,742.

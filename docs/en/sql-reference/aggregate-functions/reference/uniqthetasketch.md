---
description: 'Calculates the approximate number of different argument values, using
  the Theta Sketch Framework.'
sidebar_position: 209
slug: /sql-reference/aggregate-functions/reference/uniqthetasketch
title: 'uniqTheta'
---

Calculates the approximate number of different argument values, using the [Theta Sketch Framework](https://datasketches.apache.org/docs/Theta/ThetaSketches.html#theta-sketch-framework).

```sql
uniqTheta(x[, ...])
```

**Arguments**

The function takes a variable number of parameters. Parameters can be `Tuple`, `Array`, `Date`, `DateTime`, `String`, or numeric types.

**Returned value**

- A [UInt64](../../../sql-reference/data-types/int-uint.md)-type number.

**Implementation details**

Function:

- Calculates a hash for all parameters in the aggregate, then uses it in calculations.

- Uses the [KMV](https://datasketches.apache.org/docs/Theta/InverseEstimate.html) algorithm to approximate the number of different argument values.

        4096(2^12) 64-bit sketch are used. The size of the state is about 41 KB.

- The relative error is 3.125% (95% confidence), see the [relative error table](https://datasketches.apache.org/docs/Theta/ThetaErrorTable.html) for detail.

**See Also**

- [uniq](/sql-reference/aggregate-functions/reference/uniq)
- [uniqCombined](/sql-reference/aggregate-functions/reference/uniqcombined)
- [uniqCombined64](/sql-reference/aggregate-functions/reference/uniqcombined64)
- [uniqHLL12](/sql-reference/aggregate-functions/reference/uniqhll12)
- [uniqExact](/sql-reference/aggregate-functions/reference/uniqexact)

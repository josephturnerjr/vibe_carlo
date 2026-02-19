# vibe_carlo Phase 2: Saved snapshots

## Overview
As a user, I want to see how my financial state MAY progress - via monte
carlo simulations - but i also want to see how my financial state HAS
progressed, by providing income and asset information multiple times
over a period of months or years and comparing that to earlier
simulations. This initiative implements these new capabilities in
vibe_carlo.

## Snapshots
At its simplest, a snapshot is the set of parameters used as input to a
simulation, along with a date of when the snapshot was taken. 

Creating a new snapshot should happen on the same page as a simulation
run. Adding the values does not automatically save a snapshot, because a
user may want to play around with parameters. However, the user should
be given the opportunity to save a snapshot after entering their data.
When saving a snapshot, they should be prompted to enter the date of the
sanpshot. When a user attempts to save a snapshot, it should be
validated before being stored in the database.

Saved snapshots should be viewable in a table. The table should show all
parameters from the snapshot. For parameters that are a distribution,
like spending, it should show a small visualization of the parameter,
rather than all of the distribution parameters. Fixed distributions
should simply say `Fixed(<value set by user>)`.

A snapshot in the table should be loadable into the simulation page,
from which a user can run a simulation, play with parameters, etc. When
a snapshot is loaded in this way, the user should be able to update the
existing snapshot (though not required).

A snapshot in the table should be able to be deleted.


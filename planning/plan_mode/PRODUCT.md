# vibe_carlo: plan mode

## Overview

As a user, I can currently evaluate my past (via the timeline view) and
the future (via monte carlo simulation). My future view is limited,
however, in that it assumes that the set of parameters from my snapshot
will remain the same in the future. This makes it challenging to, say,
plan a retirement 5 years from now.

This initiative adds a new primative, a Plan, and associated views to
enable the user to create simulations where the parameters change at
fixed points in the future. 

## Plans

A Plan is an ordered list of simulation parameter sets, each of which
except the final parameter set is associated with a duration in years. 

A Plan can be simulated, just like a normal parameter set. When a Plan
is simulated, the first set of parameters is used for the duration
indicated, at which point the second set is used for the duration
indicated, and so on. The final set is used for any remaining years left
in the simulation. In this way, financial futures can be evaluated
with future events and life changes included.

## Viewing plans

There should be a new top-level nav with an associated route for plans.

The Plans page should show a table of all plans. The columns should
include the plan name and number of associated parameter sets.

There should be a button on this page to create a new Plan.

Plan rows should be able to be deleted via an icon on the Plan table
row.

Clicking a plan row should take you to the authoring page, allowing the
user to update that plan.

A Plan Simulation should be able to be run via an icon on the Plan table
row. When a Plan Simulation is run, it should route to a new page that
displays the usual fan graph, histogram, and survivor statistics that
already display on the Simulation page.

## Authoring Plans

A user authors a plan by defining a name for the plan, one or more simulation parameter sets
along with a name for each parameter set,
specifying an order for them, and specifying durations for all but the
last.

The normal parameter input form can be reused for authoring the
parameter sets.

Alongside the parameter authoring form, there should be a table that
shows the parameter sets associated with the plans. This table should
show the parameter set name and the associated values, similar to how
the snapshot table is formatted. The parameter sets
should be displayed in their defined order. A parameter set row in the
table should be able to be dragged to change the order of the parameter
set. Within the table, there should be a form element for each row to
define the number of years it is active. The last row in the table
should not display such a form, though the row may contain the form
value - the engine should ignore the value. In that way, a row dragged
to the end will not have the form appear, but will retain any duration
data the user had previously set.

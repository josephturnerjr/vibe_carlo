# vibe_carlo epic: Timeline view

## Overview

As a user, I want to see how my financial position progresses over time.
Currently, I can see how, from any given snapshot, my financial position
MAY evolve, by way of a distribution created by the Monte Carlo
simulations. However, by saving repeated snapshots, I can also see a
concrete progression of my financial position. Combining these two views
is even more powerful: from a given starting point, I can project the
future, and when the future arrives I can compare my actual results to
the distribution predicted. This initiative implements this view of
financial results AND predictions: the Timeline view.


## Timeline view

The user should have access to a new page in vibe_carlo: the Timeline
view. This view shows a timeline of the user's financial position,
including both past and future.

This should be a new route and top-level navigation item.

### History

Each snapshot captures both net portfolio value and rate of change of
the portfolio. By plotting the snapshots' portfolio values  against their dates, we can see
the progression of wealth.

### Historical distribution

For each snapshot, it is either the newest snapshot, or there are newer
snapshots. In the second case, we can simulate from the snapshot forward in time to the
date of the next-oldest snapshot to get a distribution of possible
returns (given our assumptions about the financial modeling). By showing
this distribution, it gives us more context about the next-oldest
snapshot: how well did we do relative to what we could have done?

### Future distribution

For the newest snapshot, we can project forward to get an idea of how
our historical trajectory may change and how we expect to do in the
future.

### The actual view

Combining these three views into a single graph is an interesting
challenge, but offers the user a lot of value. We can start with the
easy parts: a line graph showing each of the snapshots' portfolio values
against their dates, combined with a fan chart showing the
distribution of returns for 30 years into the future from the newest
snapshot. For the historical distributions, we should show a vertical
line (or even better - a violin plot) around the snapshot data point
showing the distribution projected from the previous point. For the
first point, there will be no such distribution. We should also label
the points with the percentile they achieved within that distribution.

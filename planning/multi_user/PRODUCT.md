# vibe_carlo: multi-user support

## Overview

Multiple users now want to use vibe_carlo. Today, the application is
architected as a single-user application, so data is not segmented.
Changing that assumption presents several new challenges:

* Data segmentation: Financial data is sensitive and the implementation
  will need to ensure that one user cannot see another user's data.
* Performance: Today, simulations run within the web worker process.
  With multiple users using the platform at once, this may exhaust web
  workers, causing outages.
* Security: Enforcing rules to ensure the security and safety of our
  users is paramount

Some expectations at this point: there will not be a lot of users, at
least initially. You can expect concurrent users to be fewer than 10 at
all times.

## Login

For now, login will be via username and password.

Users should be created on the command line, so no user creation flow is
required. Password resets will also be handled by an admin in this way.
A script for managing users (creating, deleting, changing password, etc)
should be part of this work.

## Performance

Analyze the performance of the app and make a decision about whether new
infrastructure is required given the concurrent users assumption above.
Prefer no new infra unless it is required

## Security

Use all best practices for password creation and storage. Carefully
review and be explicit about the security requirements.

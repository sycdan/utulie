# state

Reads and writes a utulie state repo. The state repo is the durable artifact —
the app is replaceable, this is what you own.

```
kb/<id>.md                 identity, KINGSMetaL frontmatter
.utulie/<name>/            a container; holds `.container` naming its id
.utulie/<name>/<name>      an item placement; names its id, and its quantity
                           when the item is fungible
```

**The tree records home. `meta.position` records where the thing actually was
last seen.** Those two disagreeing is what "checked out" means, so don't
collapse them.

Names are ids until somebody renames them, which makes KINGSMetaL's
(kind, name) uniqueness hold by construction. A rename edits the kb `name`
field and moves the tree entry in one commit; it is the only place uniqueness
needs enforcing. A fresh repo is therefore all hex, and gets readable as you
name the things you care about.

`.container` is not decoration. Git does not track empty directories, so
without it an empty bin has no existence at all — create one and it is absent
from the commit; empty one by checking out its last item and it disappears
along with its home. Which bins are empty is exactly what you need to know when
deciding where to put something.

## Integrity

Every placement names its id, so integrity is greppable and needs no index:

```
$ grep -rn <id> .utulie
```

| placements | meaning |
| --- | --- |
| 0 | not placed — this is what checked out looks like |
| 1 | placed, the normal case |
| >1 | legal only if the kb doc says `meta.fungible: true` |

`StateRepo.check()` applies that rule and also reports placements whose kb doc
is missing, quantities on non-fungible items, non-positive quantities, and a
tree entry whose name has drifted from its kb doc.

A placement with no kb doc is never dropped: the physical label exists in the
world, so it is surfaced as an orphan to be minted.

## Fungible items

`meta.fungible: true` on an *item* — not a kind, because a fungible thing is
still an item and mutating `kind` would collide with correcting a mistap.
Quantity lives on the placement, not the doc, so the same screw type holds
different counts in different bins.

Quantity zero is never written; the placement is removed instead. Absent and
zero must not be two spellings of one state.

Check-out does not mean anything for fungible stock. Take 3 of 20 screws and
nothing is checked out — the count is 17 and there is no record of where 3
went. That is the right trade for screws, and it is a stated non-goal rather
than a gap.

## Writes

One commit per action. The log is the audit trail, diffs stay legible, and
conflicts land per action. Moving anything — an item, or a container with all
its contents — is a pure rename with no content churn.

## Not here yet

Pushing to a remote. Git runs server-side and the phone never holds a repo, so
an offline action cannot reach the server at all; the PWA is expected to queue
locally and replay, each replayed action still its own commit.

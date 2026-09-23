import subprocess

import pytest

from .repo import (DriftError, StateError, StateRepo, distance_m, new_id,
                   slugify)


@pytest.fixture
def repo(tmp_path):
    r = StateRepo(tmp_path)
    r.init()
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path)
    return r


@pytest.fixture
def house(repo):
    """house > office > tin, plus an empty garage."""
    ids = {
        "house": repo.mint("container", "House", "the house"),
        "office": repo.mint("container", "Office", "the upstairs office"),
        "garage": repo.mint("container", "Garage", "where the bins live"),
        "tin": repo.mint("container", "Amaretti tin", "holds label stock"),
    }
    repo.place(ids["house"])
    repo.place(ids["office"], ids["house"])
    repo.place(ids["garage"], ids["house"])
    repo.place(ids["tin"], ids["office"])
    return ids


def test_mint_names_the_doc_after_its_id(repo):
    id_ = repo.mint("item", "A thing", "some thing")
    assert repo.doc(id_).name == id_


def test_mint_rejects_unknown_kind(repo):
    with pytest.raises(StateError, match="kind must be one of"):
        repo.mint("widget", "A thing", "some thing")


def test_only_items_can_be_fungible(repo):
    with pytest.raises(StateError, match="only items"):
        repo.mint("container", "Bin", "a bin", fungible=True)


def test_empty_container_survives_a_commit(repo, house):
    """Git does not track empty directories; `.container` is what saves them."""
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repo.root, capture_output=True, text=True
    ).stdout
    assert f".utulie/{house['house']}/{house['garage']}/.container" in tracked
    assert house["garage"] in repo.index()[0]


def test_path_of_walks_the_container_chain(repo, house):
    chain = [d.title for d in repo.path_of(house["tin"])]
    assert chain == ["House", "Office"]


def test_contents_lists_direct_children(repo, house):
    kids = {p.id for p in repo.contents(house["house"])}
    assert kids == {house["office"], house["garage"]}


def test_placing_a_non_fungible_item_again_moves_it(repo, house):
    """One verb. A thing that is not fungible can only be in one place."""
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.place(box, house["garage"])
    assert [p.container for p in repo.locate(box)] == [house["garage"]]


def test_placing_something_where_it_already_is_does_nothing(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    before = repo._git("rev-list", "--count", "HEAD").strip()
    repo.place(box, house["tin"])
    assert repo._git("rev-list", "--count", "HEAD").strip() == before


def test_placing_fungible_stock_somewhere_new_adds_a_placement(repo, house):
    """Being in two bins at once is the point of fungible."""
    screw = repo.mint("item", "M4 screw", "stainless", fungible=True)
    repo.place(screw, house["tin"], quantity=40)
    repo.place(screw, house["garage"], quantity=6)
    assert len(repo.locate(screw)) == 2


def test_placing_fungible_stock_where_it_is_updates_the_count(repo, house):
    screw = repo.mint("item", "M4 screw", "stainless", fungible=True)
    repo.place(screw, house["tin"], quantity=40)
    repo.place(screw, house["tin"], quantity=12)
    assert [p.quantity for p in repo.locate(screw)] == [12]


def test_fungible_item_holds_a_quantity_per_container(repo, house):
    screw = repo.mint("item", "M4 screw", "stainless pan-head", fungible=True)
    repo.place(screw, house["tin"], quantity=40)
    repo.place(screw, house["garage"], quantity=6)
    got = {p.container: p.quantity for p in repo.locate(screw)}
    assert got == {house["tin"]: 40, house["garage"]: 6}
    assert repo.check() == []


def test_quantity_is_refused_on_a_non_fungible_item(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    with pytest.raises(StateError, match="not fungible"):
        repo.place(box, house["tin"], quantity=3)


def test_quantity_zero_is_never_written(repo, house):
    screw = repo.mint("item", "M4 screw", "stainless", fungible=True)
    with pytest.raises(StateError, match="check out instead"):
        repo.place(screw, house["tin"], quantity=0)


def test_setting_quantity_to_zero_removes_the_placement(repo, house):
    screw = repo.mint("item", "M4 screw", "stainless", fungible=True)
    repo.place(screw, house["tin"], quantity=2)
    repo.set_quantity(screw, house["tin"], 0)
    assert repo.locate(screw) == []


def test_placing_something_already_placed_is_a_rename(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.place(box, house["garage"])
    assert repo.locate(box)[0].container == house["garage"]
    stat = subprocess.run(
        ["git", "show", "--stat", "-M", "--oneline", "HEAD"],
        cwd=repo.root, capture_output=True, text=True,
    ).stdout
    assert "1 file changed, 0 insertions(+), 0 deletions(-)" in stat


def test_replacing_a_container_carries_its_contents(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.place(house["tin"], house["garage"])
    assert repo.path_of(box)[-1].id == house["tin"]
    assert repo.path_of(house["tin"])[-1].id == house["garage"]


def test_a_container_cannot_be_placed_inside_itself(repo, house):
    with pytest.raises(StateError, match="inside itself"):
        repo.place(house["office"], house["tin"])


def test_check_out_leaves_the_doc_and_drops_the_placement(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.check_out(box)
    assert repo.locate(box) == []
    assert repo.doc(box).title == "Label box"   # identity survives
    assert repo.check() == []                    # unplaced is not an error


def test_rename_moves_the_kb_field_and_the_tree_entry_together(repo, house):
    repo.rename(house["garage"], "garage")
    assert repo.doc(house["garage"]).name == "garage"
    assert repo.index()[0][house["garage"]].endswith("/garage")
    assert repo.check() == []


def test_rename_rejects_a_clash_within_a_kind(repo, house):
    repo.rename(house["garage"], "garage")
    with pytest.raises(StateError, match="already named"):
        repo.rename(house["office"], "garage")


def test_a_clash_is_detected_after_slugifying(repo, house):
    """"Garage" and "garage" are the same name once slugified."""
    repo.rename(house["garage"], "garage")
    with pytest.raises(StateError, match="already named"):
        repo.rename(house["office"], "Garage")


def test_rename_allows_the_same_name_across_kinds(repo, house):
    thing = repo.mint("item", "Spare", "a spare")
    repo.rename(house["garage"], "spare")
    repo.rename(thing, "spare")          # item and container may share a name


@pytest.mark.parametrize("given,expected", [
    ("Amaretti Tin", "amaretti-tin"),
    ("  Garage  ", "garage"),
    ("../escape", "escape"),          # traversal cannot survive slugifying
    ("Café Nöir", "cafe-noir"),
    ("shelf #3", "shelf-3"),
    ("a__b", "a-b"),
])
def test_slugify(given, expected):
    assert slugify(given) == expected


def test_rename_slugifies_and_reports_what_it_used(repo, house):
    assert repo.rename(house["garage"], "Garden Shed") == "garden-shed"
    assert repo.doc(house["garage"]).name == "garden-shed"
    assert repo.index()[0][house["garage"]].endswith("/garden-shed")
    assert repo.check() == []


def test_rename_refuses_a_name_with_nothing_usable_in_it(repo, house):
    for bad in ("", "---", "!!!", "☃"):
        with pytest.raises(StateError, match="nothing usable"):
            repo.rename(house["garage"], bad)


def test_a_minted_name_is_already_a_valid_slug(repo):
    id_ = repo.mint("item", "A thing", "some thing")
    assert slugify(repo.doc(id_).name) == repo.doc(id_).name


def test_check_is_clean_on_a_healthy_repo(repo, house):
    assert repo.check() == []


def test_check_reports_a_placement_with_no_kb_doc(repo, house):
    stray = repo.root / ".utulie" / house["house"] / "mystery"
    stray.write_text(f"id: {new_id()}\n", newline="\n")
    problems = repo.check()
    assert [p.kind for p in problems] == ["orphan-placement"]


def test_check_reports_a_non_fungible_item_placed_twice(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    # forge a second placement the API refuses to create
    (repo.root / ".utulie" / house["house"] / house["garage"] / box).write_text(
        f"id: {box}\n", newline="\n"
    )
    assert [p.kind for p in repo.check()] == ["placed-twice"]


def test_check_reports_name_drift(repo, house):
    d = repo.doc(house["garage"])
    d.name = "garage"
    repo._write_doc(d)          # kb renamed, tree not
    assert [p.kind for p in repo.check()] == ["name-drift"]


def test_every_write_makes_exactly_one_commit(repo, house):
    before = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo.root, capture_output=True, text=True,
    ).stdout.strip()
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.place(box, house["garage"])
    repo.check_out(box)
    after = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo.root, capture_output=True, text=True,
    ).stdout.strip()
    assert int(after) - int(before) == 4


def test_files_are_written_with_lf(repo, house):
    raw = (repo.root / "kb" / f"{house['tin']}.md").read_bytes()
    assert b"\r\n" not in raw


def test_frontmatter_is_valid_yaml(repo):
    """Quoting is the yaml library's business; validity is ours."""
    import yaml
    id_ = repo.mint("item", "A thing", "plain prose: with a colon, and #hash")
    frontmatter = (repo.root / "kb" / f"{id_}.md").read_text().split("---\n")[1]
    assert yaml.safe_load(frontmatter)["gist"] == "plain prose: with a colon, and #hash"


def test_gist_survives_quotes_and_backslashes(repo):
    id_ = repo.mint("item", "A thing", 'a "quoted" c:\path thing')
    assert repo.doc(id_).gist == 'a "quoted" c:\path thing'


def test_field_order_follows_kingsmetal(repo):
    id_ = repo.mint("item", "Screw", "stainless", fungible=True)
    frontmatter = (repo.root / "kb" / f"{id_}.md").read_text().split("---\n")[1]
    keys = [ln.split(":")[0] for ln in frontmatter.splitlines()
            if ln and not ln.startswith(" ")]
    assert keys == ["kind", "id", "name", "gist", "meta"]


def test_ids_are_uuid7_with_a_decodable_timestamp():
    """Same format nosedive mint emits, without shelling out to it."""
    import time
    import uuid
    before = int(time.time() * 1000)
    a, b = new_id(), new_id()
    assert uuid.UUID(a).version == 7
    stamp = int(uuid.UUID(a).hex[:12], 16)
    assert before - 1000 <= stamp <= before + 1000   # leading 48 bits are the ms
    assert a < b                                      # monotonic, so ids sort by age


def test_checking_out_a_full_container_is_refused(repo, house):
    """It would delete the contents' placements as collateral."""
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    with pytest.raises(StateError, match="still holds 1 thing"):
        repo.check_out(house["tin"])
    assert len(repo.locate(box)) == 1
    assert len(repo.locate(house["tin"])) == 1


def test_an_empty_container_can_be_checked_out(repo, house):
    repo.check_out(house["garage"])
    assert repo.locate(house["garage"]) == []
    assert repo.check() == []


def test_checking_out_a_container_names_what_is_inside(repo, house):
    with pytest.raises(StateError, match="Amaretti tin"):
        repo.check_out(house["office"])


def test_undo_reverses_the_last_action(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.place(box, house["garage"])
    assert repo.undo() == "move Label box to Garage"
    assert repo.locate(box)[0].container == house["tin"]


def test_undo_restores_a_checked_out_item(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.check_out(box)
    repo.undo()
    assert repo.locate(box)[0].container == house["tin"]


def test_undo_is_itself_undoable_as_a_redo(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.check_out(box)
    repo.undo()
    repo.undo()
    assert repo.locate(box) == []


def test_undo_keeps_the_history_rather_than_rewriting_it(repo, house):
    before = repo._git("rev-list", "--count", "HEAD").strip()
    box = repo.mint("item", "Label box", "a box of labels")
    repo.undo()
    after = repo._git("rev-list", "--count", "HEAD").strip()
    assert int(after) == int(before) + 2      # the action, then its undo


def test_undo_refuses_on_a_fresh_repo(repo):
    with pytest.raises(StateError, match="nothing to undo"):
        repo.undo()


GARAGE_POS = (43.653200, -79.383200)
SHED_POS = (43.653500, -79.383900)      # ~65 m away


def test_position_is_recorded_with_when(repo, house):
    repo.set_position(house["garage"], *GARAGE_POS)
    pos = repo.doc(house["garage"]).meta["position"]
    assert (pos["lat"], pos["lon"]) == GARAGE_POS
    assert pos["at"].endswith("Z")


def test_position_rejects_a_non_coordinate(repo, house):
    with pytest.raises(StateError, match="not a coordinate"):
        repo.set_position(house["garage"], 91.0, 0.0)


def test_an_item_inherits_the_position_of_its_container(repo, house):
    """You geotag the bin, not every screw in it."""
    repo.set_position(house["office"], *GARAGE_POS)
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    pos, source = repo.position_of(box)
    assert (pos["lat"], pos["lon"]) == GARAGE_POS
    assert source.id == house["office"]          # says who supplied the answer


def test_a_things_own_position_beats_its_containers(repo, house):
    repo.set_position(house["office"], *GARAGE_POS)
    repo.set_position(house["tin"], *SHED_POS)
    _, source = repo.position_of(house["tin"])
    assert source.id == house["tin"]


def test_nearest_container_wins_over_a_more_distant_ancestor(repo, house):
    repo.set_position(house["house"], *GARAGE_POS)
    repo.set_position(house["office"], *SHED_POS)
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    _, source = repo.position_of(box)
    assert source.id == house["office"]


def test_position_is_none_when_nothing_up_the_chain_has_one(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    assert repo.position_of(box) is None


def test_distance_between_two_positions(repo):
    a = {"lat": GARAGE_POS[0], "lon": GARAGE_POS[1]}
    b = {"lat": SHED_POS[0], "lon": SHED_POS[1]}
    assert 60 < distance_m(a, b) < 70
    assert distance_m(a, a) == 0.0


def test_setting_a_position_is_one_commit(repo, house):
    before = int(repo._git("rev-list", "--count", "HEAD").strip())
    repo.set_position(house["garage"], *GARAGE_POS)
    assert int(repo._git("rev-list", "--count", "HEAD").strip()) == before + 1


def test_head_changes_with_every_action(repo, house):
    before = repo.head()
    repo.mint("item", "A thing", "some thing")
    assert repo.head() != before


def test_a_write_against_the_current_head_is_allowed(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"], expect=repo.head())
    assert repo.locate(box)[0].container == house["tin"]


def test_a_write_against_a_stale_head_is_refused(repo, house):
    """Read, someone else writes, then you write: your view was stale."""
    stale = repo.head()
    box = repo.mint("item", "Label box", "a box of labels")     # the other writer
    with pytest.raises(DriftError, match="state moved"):
        repo.place(box, house["tin"], expect=stale)


def test_a_refused_write_changes_nothing(repo, house):
    stale = repo.head()
    box = repo.mint("item", "Label box", "a box of labels")
    head_before = repo.head()
    with pytest.raises(DriftError):
        repo.place(box, house["tin"], expect=stale)
    assert repo.head() == head_before
    assert repo.locate(box) == []


def test_drift_reports_both_shas_so_a_client_can_explain_itself(repo, house):
    stale = repo.head()
    repo.mint("item", "A thing", "some thing")
    try:
        repo.rename(house["garage"], "garage", expect=stale)
    except DriftError as e:
        assert e.expected == stale
        assert e.actual == repo.head()
    else:
        pytest.fail("expected DriftError")


def test_a_short_sha_matches(repo, house):
    repo.rename(house["garage"], "garage", expect=repo.head()[:8])


def test_omitting_expect_writes_unconditionally(repo, house):
    repo.mint("item", "A thing", "some thing")
    repo.rename(house["garage"], "garage")      # no expect, no complaint


def test_delete_erases_doc_and_placement(repo, house):
    """For a mistap. Check-out keeps the identity; delete does not."""
    box = repo.mint("item", "Oops", "minted by mistake")
    repo.place(box, house["tin"])
    repo.delete(box)
    assert repo.locate(box) == []
    with pytest.raises(StateError, match="no kb doc"):
        repo.doc(box)
    assert repo.check() == []


def test_delete_refuses_a_container_with_contents(repo, house):
    with pytest.raises(StateError, match="still holds"):
        repo.delete(house["office"])


def test_delete_works_on_something_never_placed(repo, house):
    stray = repo.mint("container", "Oops", "minted by mistake")
    repo.delete(stray)
    assert stray not in repo.docs()


def test_undo_twice_is_a_redo_not_two_steps_back(repo, house):
    """LIFO on commits. Repeated undo toggles; it does not walk back."""
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.undo()
    assert repo.locate(box) == []
    repo.undo()
    assert repo.locate(box)[0].container == house["tin"]


def test_placing_zero_on_an_existing_fungible_placement_removes_it(repo, house):
    """Same rule set_quantity(...,0) already follows. place() must honor it too."""
    screw = repo.mint("item", "M4 screw", "stainless", fungible=True)
    repo.place(screw, house["tin"], quantity=40)
    repo.place(screw, house["tin"], quantity=0)
    assert repo.locate(screw) == []


def test_placing_zero_on_a_fresh_fungible_placement_is_still_refused(repo, house):
    """Zero only makes sense as "remove what is there." There is nothing to
    remove for a placement that does not exist yet."""
    screw = repo.mint("item", "M4 screw", "stainless", fungible=True)
    with pytest.raises(StateError, match="check out instead"):
        repo.place(screw, house["tin"], quantity=0)


def test_deleting_the_last_kb_doc_leaves_kb_usable(repo, house):
    """git prunes a directory once its last tracked file is gone. Deleting
    the only doc must not take kb/ down with it -- a subsequent mint has to
    still work.

    init()'s own kb/.gitkeep already guards a freshly-initialised repo, so
    that alone would pass even without delete()'s self-heal. Remove it here
    to stand in for a repo created before that fix -- the case delete()'s
    self-heal exists for -- so this test actually exercises delete()'s own
    responsibility, not init()'s."""
    (repo.root / "kb" / ".gitkeep").unlink()
    repo._commit("simulate a pre-fix repo with no kb/.gitkeep")
    for id_ in ["tin", "office", "garage", "house"]:  # children before parents
        repo.delete(house[id_])
    assert (repo.root / "kb").is_dir()
    survivor = repo.mint("container", "Shed", "minted after the purge")
    assert survivor in repo.docs()


def test_sync_status_with_no_upstream(repo):
    """A fresh repo (or a dev clone never pushed with -u) has no upstream
    at all -- distinct from an upstream that is 0 commits ahead."""
    status = repo.sync_status()
    assert status["upstream"] is None
    assert status["ahead"] == 0
    assert status["branch"] == repo._git("rev-parse", "--abbrev-ref", "HEAD").strip()


def test_sync_status_zero_ahead_of_a_real_upstream(repo, tmp_path):
    bare = tmp_path / "_bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)])
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo.root)
    branch = repo._git("rev-parse", "--abbrev-ref", "HEAD").strip()
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=repo.root,
                    capture_output=True, text=True)
    status = repo.sync_status()
    assert status["upstream"] is not None
    assert status["ahead"] == 0


def test_set_title_changes_the_h1(repo, house):
    repo.set_title(house["tin"], "Amaretti Tin (relabelled)")
    assert repo.doc(house["tin"]).title == "Amaretti Tin (relabelled)"


def test_set_title_refuses_empty(repo, house):
    with pytest.raises(StateError, match="cannot be empty"):
        repo.set_title(house["tin"], "   ")


def test_set_gist_changes_the_gist(repo, house):
    repo.set_gist(house["tin"], "holds spare label stock")
    assert repo.doc(house["tin"]).gist == "holds spare label stock"


def test_set_gist_can_clear_to_empty(repo, house):
    repo.set_gist(house["tin"], "")
    assert repo.doc(house["tin"]).gist == ""


def test_sync_status_counts_commits_ahead(repo, tmp_path, house):
    bare = tmp_path / "_bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)])
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo.root)
    branch = repo._git("rev-parse", "--abbrev-ref", "HEAD").strip()
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=repo.root,
                    capture_output=True, text=True)
    repo.mint("item", "Unsynced thing", "made after the push")
    assert repo.sync_status()["ahead"] == 1

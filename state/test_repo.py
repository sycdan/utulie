import subprocess

import pytest

from .repo import StateError, StateRepo


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


def test_non_fungible_item_is_placed_exactly_once(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    assert len(repo.locate(box)) == 1
    with pytest.raises(StateError, match="already placed"):
        repo.place(box, house["garage"])


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


def test_move_is_a_rename(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.move(box, house["garage"])
    assert repo.locate(box)[0].container == house["garage"]
    stat = subprocess.run(
        ["git", "show", "--stat", "-M", "--oneline", "HEAD"],
        cwd=repo.root, capture_output=True, text=True,
    ).stdout
    assert "1 file changed, 0 insertions(+), 0 deletions(-)" in stat


def test_moving_a_container_carries_its_contents(repo, house):
    box = repo.mint("item", "Label box", "a box of labels")
    repo.place(box, house["tin"])
    repo.move(house["tin"], house["garage"])
    assert repo.path_of(box)[-1].id == house["tin"]
    assert repo.path_of(house["tin"])[-1].id == house["garage"]


def test_a_container_cannot_be_moved_inside_itself(repo, house):
    with pytest.raises(StateError, match="inside itself"):
        repo.move(house["office"], house["tin"])


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


def test_rename_allows_the_same_name_across_kinds(repo, house):
    thing = repo.mint("item", "Spare", "a spare")
    repo.rename(house["garage"], "spare")
    repo.rename(thing, "spare")          # item and container may share a name


def test_rename_rejects_names_that_are_not_path_safe(repo, house):
    for bad in ("Garage", "the garage", "../escape", ""):
        with pytest.raises(StateError, match="name must match"):
            repo.rename(house["garage"], bad)


def test_check_is_clean_on_a_healthy_repo(repo, house):
    assert repo.check() == []


def test_check_reports_a_placement_with_no_kb_doc(repo, house):
    stray = repo.root / ".utulie" / house["house"] / "mystery"
    stray.write_text("id: 01a0c5ff-0000-7000-8000-000000000000\n", newline="\n")
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
    repo.move(box, house["garage"])
    repo.check_out(box)
    after = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo.root, capture_output=True, text=True,
    ).stdout.strip()
    assert int(after) - int(before) == 4


def test_files_are_written_with_lf(repo, house):
    raw = (repo.root / "kb" / f"{house['tin']}.md").read_bytes()
    assert b"\r\n" not in raw


def test_gist_is_always_quoted(repo):
    """KINGSMetaL quotes prose values; safe_dump only quotes when forced."""
    id_ = repo.mint("item", "A thing", "plain prose needing no escape")
    raw = (repo.root / "kb" / f"{id_}.md").read_text()
    assert 'gist: "plain prose needing no escape"' in raw


def test_gist_survives_quotes_and_backslashes(repo):
    id_ = repo.mint("item", "A thing", 'a "quoted" c:\path thing')
    assert repo.doc(id_).gist == 'a "quoted" c:\path thing'


def test_field_order_follows_kingsmetal(repo):
    id_ = repo.mint("item", "Screw", "stainless", fungible=True)
    frontmatter = (repo.root / "kb" / f"{id_}.md").read_text().split("---\n")[1]
    keys = [ln.split(":")[0] for ln in frontmatter.splitlines()
            if ln and not ln.startswith(" ")]
    assert keys == ["kind", "id", "name", "gist", "meta"]

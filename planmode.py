from __future__ import annotations
from pydantic import BaseModel, Field
from pathlib import Path
import fasthtml.common as fh
import os


def slug(txt: str) -> str:
    return txt.lower().replace(" ", "-").replace(".", "")


REPOS: dict[str, Path] = {
    slug((path / "index.md").read_text().split("\n")[0][2:]): path
    for path in map(Path, os.getenv("REPOS", "").split(":"))
}

TITLE = {
    "goals": "Goals",
    "status": "Status",
    "problems": "Problems",
    "tasks": "Tasks",
}

app, rt = fh.fast_app(live=True, debug=True)


def md_section(md: str, head: str) -> str:
    h = head.split(" ")[0]
    assert h == "#" * len(h)
    assert head in md
    md = md.split(head, maxsplit=1)[1]
    for line in md.splitlines():
        if not line.startswith(f"{h} "):
            continue
        md_head = md.split(line)[0]
        break
    else:
        md_head = md
    md_head = md_head.replace(head, "").strip()
    return md_head


class Item(BaseModel):
    name: str
    items: list[Item] = []

    def to_md(self, indent: int = 0) -> str:
        prefix = "  " * indent
        lines = [f"{prefix}- {self.name}"]
        for item in self.items:
            lines.append(item.to_md(indent + 1))
        return "\n".join(lines)

    @classmethod
    def from_md(cls, md: str) -> list[Item]:
        md = md.strip()
        if not md:
            return []
        assert md.startswith("- "), f"Text is not a nested list!\n{md}"
        md = "\n" + md
        items = []
        for item_md in md.split("\n- ")[1:]:
            parts = item_md.split("\n", maxsplit=1)
            name = parts[0]
            if len(parts) == 1:
                items.append(Item(name=name, items=[]))
                continue
            items_md = "\n".join(line[2:] for line in parts[1].splitlines())
            items.append(Item(name=name, items=Item.from_md(items_md)))
        return items


class Plan(BaseModel):
    repo: str
    path: Path
    name: str
    goals: list[Item] = Field(default_factory=list)
    plans: list[Plan] = Field(default_factory=list)
    status: list[Item] = Field(default_factory=list)
    problems: list[Item] = Field(default_factory=list)
    tasks: list[Item] = Field(default_factory=list)

    def to_md(self):
        md_status = "\n".join(item.to_md() for item in self.goals)
        return "\n".join([
            f"# {self.name}\n",
            "## Goals\n",
            "\n".join(item.to_md() for item in self.goals),
            "\n## Status\n",
            md_status,
            "\n## Problems\n",
            "\n".join(item.to_md() for item in self.problems),
            "\n## Tasks\n",
            "\n".join(item.to_md() for item in self.tasks),
        ])

    @classmethod
    def from_path(cls, repo: str, subpath: Path) -> Plan:
        path = REPOS[repo] / subpath if subpath else REPOS[repo]
        if path.is_file():
            return Plan.from_md(path.read_text(), repo, subpath)
        index_md = path / "index.md"
        plan = Plan.from_md(index_md.read_text(), repo, subpath)
        plan.plans = [
            Plan.from_path(repo, d.relative_to(REPOS[repo]))
            for d in path.iterdir()
            if d.is_dir()
        ]
        plan.plans += [
            Plan.from_md(f.read_text(), repo, f.relative_to(REPOS[repo]))
            for f in path.iterdir()
            if f.is_file() and f.name != "index.md"
        ]
        plan.plans.sort(key=lambda p: p.name.lower())
        return plan

    @classmethod
    def from_md(cls, md: str, repo: str, path: Path) -> Plan:
        # Determine project name.
        md = md.strip()
        assert md.startswith("# "), (
            f"Unable to determine project name! {repo=}, {path=}"
        )
        name, md = md[2:].split("\n", maxsplit=1)

        # Determine project goals.
        md_goals = md_section(md, "## Goals")
        goals = Item.from_md(md_goals)

        # Determine project status.
        md_status = md_section(md, "## Status")
        status = Item.from_md(md_status)

        # Determine project problems.
        md_problems = md_section(md, "## Problems")
        problems = Item.from_md(md_problems)

        # Determine project tasks.
        md_tasks = md_section(md, "## Tasks")
        tasks = Item.from_md(md_tasks)

        return Plan(
            repo=repo,
            path=path,
            name=name,
            goals=goals,
            status=status,
            problems=problems,
            tasks=tasks,
        )


def body(*args, current_path="/", current_view=""):
    items = [
        ("Index", ""),
        ("Plan", "plan"),
        ("Goals", "goals"),
        ("Status", "status"),
        ("Problems", "problems"),
        ("Tasks", "tasks"),
        ("All", "all"),
    ]

    def link(label, view):
        if current_view == view:
            return fh.Li(label)
        href = "/" if view == "" else f"{current_path}?view={view}"
        return fh.Li(fh.A(label, href=href))

    return fh.Body(
        fh.Style("html { scrollbar-gutter: stable; }"),
        fh.Container(
            fh.Nav(
                fh.Ul(*[link(label, foo) for label, foo in items]),
            ),
            fh.Main(*args),
        ),
    )


def render_items(items: list[Item]):
    return fh.Ul(fh.Li(i.name, render_items(i.items)) for i in items)


def view_plan(repo, path):
    def Section(title: str, items: list[Item]):
        return fh.Section(fh.H2(title), render_items(items))

    plan = Plan.from_path(repo, path)
    return body(
        fh.H1(plan.name),
        Section("Goals", plan.goals),
        fh.Section(
            fh.H2("Plans"),
            fh.Ul(fh.Li(fh.A(p.name, href=f"/{p.repo}/{p.path}")) for p in plan.plans),
        ),
        Section("Status", plan.status),
        Section("Problems", plan.problems),
        Section("Tasks", plan.tasks),
        current_path=f"/{repo}/{path}",
        current_view="plan",
    )


def render_section(repo: str, current_path: Path, plan: Plan, section, index=0):
    h = (
        [fh.H3, fh.H4, fh.H5, fh.H6][index](
            fh.A(plan.name, href=f"/{repo}/{plan.path}?view=plan")
        )
        if plan.path != current_path
        else None
    )
    return fh.Section(
        h,
        render_items(
            getattr(plan, section),
        ),
        *[
            render_section(repo, current_path, p, section, index + 1)
            for p in plan.plans
        ],
    )


def view_section(repo, path, view):
    plan = Plan.from_path(repo, path)
    return body(
        fh.H1(f"{plan.name}: {TITLE[view]}"),
        render_section(repo, path, plan, view),
        current_path=f"/{repo}/{path}",
        current_view=f"{view}",
    )


def view_all(repo, path):
    def Section(title: str, section: str):
        return fh.Section(fh.H2(title), render_section(repo, path, plan, section))

    plan = Plan.from_path(repo, path)
    return body(
        fh.H1(plan.name),
        Section("Goals", "goals"),
        Section("Status", "status"),
        Section("Problems", "problems"),
        Section("Tasks", "tasks"),
        current_path=f"/{repo}/{path}",
        current_view="all",
    )


def view_index():
    def Plans(plans: list[Plan]):
        return fh.Ul(
            fh.Li(fh.A(p.name, href=f"/{p.repo}/{p.path}"), Plans(p.plans))
            for p in plans
        )

    plans = [Plan.from_path(name, Path(".")) for name, path in REPOS.items()]
    return fh.Container(
        fh.H1("PlanMode"), Plans(plans), current_path="/", current_view=""
    )


@rt("/")
def get(view: str = ""):
    return view_index()


@rt("/{repo:str}/{path:path}")
def get(repo: str, path: Path, view: str = "plan"):
    if view == "plan":
        return view_plan(repo, path)
    if view in ("goals", "status", "problems", "tasks"):
        return view_section(repo, path, view)
    if view == "all":
        return view_all(repo, path)


if __name__ == "__main__":
    fh.serve(port=80)

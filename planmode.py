from __future__ import annotations
from pydantic import BaseModel, Field
from pathlib import Path
import typer
import fasthtml.common as fh
import os


pm = typer.Typer()

app, rt = fh.fast_app()

REPO: Path = Path(os.environ.get("PLANMODE_REPO", "."))


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
    def from_path(cls, path: Path) -> Plan:
        if path.is_file():
            return Plan.from_md(path.read_text(), path.relative_to(REPO))
        index_md = path / "index.md"
        assert index_md.is_file(), (
            f"Index file is missing! {index_md.relative_to(REPO)}"
        )
        plan = Plan.from_md(index_md.read_text(), index_md.relative_to(REPO))
        plan.plans = [Plan.from_path(d) for d in path.iterdir() if d.is_dir()]
        plan.plans += [
            Plan.from_md(f.read_text(), f.relative_to(REPO))
            for f in path.iterdir()
            if f.is_file() and f.name != "index.md"
        ]
        plan.plans.sort(key=lambda p: p.name.lower())
        return plan

    @classmethod
    def from_md(cls, md: str, path: Path) -> Plan:
        # Assert sections are present.
        assert "## Goals\n" in md, f"Section '## Goals' missing! {path}"
        assert "## Status\n" in md, f"Section '## Status' missing! {path}"
        assert "## Problems\n" in md, f"Section '## Problems' missing! {path}"
        assert "## Tasks\n" in md, f"Section '## Tasks' missing! {path}"

        # Determine project name.
        md = md.strip()
        assert md.startswith("# "), f"Unable to determine project name! {path}"
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
            path=path if path.name != "index.md" else path.parent,
            name=name,
            goals=goals,
            status=status,
            problems=problems,
            tasks=tasks,
        )


@pm.command()
def serve():
    fh.serve()


def body(*args, current="/"):
    items = [
        ("Index", "/"),
        ("Plans", "/plans"),
        ("Goals", "/goals"),
        ("Status", "/status"),
        ("Problems", "/problems"),
        ("Tasks", "/tasks"),
    ]

    def link(label, href):
        attrs = {"aria-current": "page"} if current == href else {}
        return fh.Li(fh.A(label, href=href, **attrs))

    return fh.Body(
        fh.Nav(
            fh.Ul(*[link(label, href) for label, href in items]),
        ),
        fh.Main(*args),
    )


@rt("/")
def get():
    def Plans(plans: list[Plan]):
        return fh.Ul(
            fh.Li(fh.A(p.name, href=f"/plans/{p.path}"), Plans(p.plans)) for p in plans
        )

    try:
        plan = Plan.from_path(REPO)
    except Exception as error:
        return error
    return body(fh.H1("PlanMode"), Plans([plan]), current="/")


def render_items(items: list[Item]):
    return fh.Ul(fh.Li(i.name, render_items(i.items)) for i in items)


@rt("/plans/{filepath:path}")
def get(filepath: Path):
    def Section(title: str, items: list[Item]):
        return fh.Section(fh.H2(title), render_items(items))

    try:
        plan = Plan.from_path(REPO / filepath)
    except Exception as error:
        return error
    return body(
        fh.H1(plan.name),
        Section("Goals", plan.goals),
        fh.Section(
            fh.H2("Plans"),
            fh.Ul(fh.Li(fh.A(p.name, href=f"/plans/{p.path}")) for p in plan.plans),
        ),
        Section("Status", plan.status),
        Section("Problems", plan.problems),
        Section("Tasks", plan.tasks),
        current="/plans",
    )


@rt("/{section:str}/{filepath:path}")
def get(section: str, filepath: Path):
    def Section(plan: Plan, attr, index=0):
        h = [fh.H1, fh.H3, fh.H4, fh.H5, fh.H6][index]
        return fh.Section(
            h(plan.name),
            render_items(
                getattr(plan, attr),
            ),
            *[Section(p, attr, index + 1) for p in plan.plans],
        )

    try:
        plan = Plan.from_path(REPO / filepath)
    except Exception as error:
        return error
    return body(Section(plan, section), current=f"/{section}")


if __name__ == "__main__":
    pm()

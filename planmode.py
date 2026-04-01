from __future__ import annotations

import os
from pathlib import Path

import fasthtml.common as fh
import glom
import monsterui.all as mui
from pydantic import BaseModel, Field


def slug(txt: str) -> str:
    return (
        txt
        .lower()
        .replace(" ", "-")
        .replace(".", "-")
        .replace("/", "-")
        .replace(":", "-")
        .strip("-")
    )


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

DEBUG = False
app, rt = fh.fast_app(hdrs=mui.Theme.blue.headers(), live=DEBUG, debug=DEBUG)


class Item(BaseModel):
    parent: Item | Section
    spec: str
    name: str
    items: list[Item] = Field(default_factory=list)

    def to_md(self, indent: int = 0) -> str:
        prefix = "  " * indent
        lines = [f"{prefix}- {self.name}"]
        for item in self.items:
            lines.append(item.to_md(indent + 1))
        return "\n".join(lines)

    @classmethod
    def from_md(cls, md: str, parent: Item | Section) -> list[Item]:
        md = md.strip()
        if not md:
            return []
        assert md.startswith("- "), f"Text is not a nested list!\n{md}\n{parent}"
        md = "\n" + md
        items: list[Item] = []
        for i, item_md in enumerate(md.split("\n- ")[1:]):
            parts = item_md.split("\n", maxsplit=1)
            name = parts[0]
            spec = f"{parent.spec}.items.{i}"
            if len(parts) == 1:
                items.append(Item(parent=parent, spec=spec, name=name))
                continue
            i = Item(parent=parent, spec=spec, name=name)
            i.items = Item.from_md(
                "\n".join(line[2:] for line in parts[1].splitlines()), parent=i
            )
            items.append(i)
        return items

    def to_html(self, href: str):
        html = []
        in_code = False
        for part in self.name.split("`"):
            if not in_code:
                html += [fh.Span(part)]
                in_code = True
                continue
            if in_code:
                html += [fh.Code(part)]
                in_code = False
                continue

        print(html)
        if " [http" in str(html[-1]) and str(html[-1]).endswith("]</span>"):
            parts = str(html[-1])[len("<span>") :].split(" [http")
            html[-1] = parts[0]
            html = [
                fh.A(
                    *html,
                    href="http" + parts[1][: -len("]</span>")],
                    cls="text-blue-500",
                )
            ]

        return fh.Div(
            fh.Div(
                Del(href, f"{self.spec}"),
                fh.Nbsp(),
                fh.Span(*html, cls="w-full"),
                Add(href, f"{self.spec}.items"),
                cls="flex",
            ),
            fh.Div(
                *[i.to_html(href) for i in self.items],
                cls="pl-6",
                id=slug(f"{href}:{self.spec}.items"),
            ),
            id=slug(f"{href}:{self.spec}"),
        )


class Section(BaseModel):
    href: str
    spec: str = ""
    title: str = ""
    items: list[Item] = Field(default_factory=list)

    def to_md(self):
        return "\n".join([
            f"\n## {self.title}\n",
            "\n".join(item.to_md() for item in self.items),
        ])

    @classmethod
    def from_md(cls, href: str, md: str):
        def md_section(md: str, title: str) -> str:
            h = title.split(" ")[0]
            assert h == "#" * len(h)
            assert title in md
            md = md.split(title, maxsplit=1)[1]
            for line in md.splitlines():
                if not line.startswith(f"{h} "):
                    continue
                md_head = md.split(line)[0]
                break
            else:
                md_head = md
            md_head = md_head.replace(title, "").strip()
            return md_head

        section = cls(href=href)
        section.items = Item.from_md(md_section(md, f"## {section.title}"), section)
        return section

    def items_to_html(self):
        return fh.Div(
            *[i.to_html(self.href) for i in self.items],
            id=slug(f"{self.href}-{self.spec}-items"),
        )

    def to_html(self, view):
        query = "" if view == self.spec else f"?view={self.spec}"
        return mui.Section(
            fh.Header(
                mui.H2(
                    fh.A(self.title, href=f"{self.href}{query}#{self.spec}"),
                    cls="w-full",
                ),
                Add(self.href, f"{self.spec}.items"),
                cls="flex pt-6 pb-3 items-end",
            ),
            self.items_to_html(),
            id=self.spec,
        )


class Goals(Section):
    spec: str = "goals"
    title: str = "Goals"


class Status(Section):
    spec: str = "status"
    title: str = "Status"


class Problems(Section):
    spec: str = "problems"
    title: str = "Problems"


class Tasks(Section):
    spec: str = "tasks"
    title: str = "Tasks"


class Plan(BaseModel):
    repo: str
    path: Path
    href: str
    name: str
    plans: list[Plan] = Field(default_factory=list)
    goals: Goals
    status: Status
    problems: Problems
    tasks: Tasks

    def __getitem__(self, key: str):
        return getattr(self, key)

    def to_md(self):
        return "\n".join([
            f"# {self.name}",
            self.goals.to_md() if self.goals else "",
            self.status.to_md() if self.status else "",
            self.problems.to_md() if self.problems else "",
            self.tasks.to_md() if self.tasks else "",
        ])

    def write(self):
        path = REPOS[self.repo] / self.path
        if path.is_dir():
            path = path / "index.md"
        path.write_text(self.to_md())

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
        md = md.strip()
        assert md.startswith("# "), (
            f"Unable to determine project name! {repo=}, {path=}"
        )
        name, md = md[2:].split("\n", maxsplit=1)
        href = f"/{repo}/{path}"
        plan = Plan(
            repo=repo,
            path=path,
            href=href,
            name=name,
            goals=Goals.from_md(href=href, md=md),
            status=Status.from_md(href=href, md=md),
            problems=Problems.from_md(href=href, md=md),
            tasks=Tasks.from_md(href=href, md=md),
        )
        return plan


def body(*args, current_path="/", current_view=""):
    return fh.Body(
        fh.Style("html { scrollbar-gutter: stable; }"),
        mui.Container(
            fh.Nav(
                fh.Ul(
                    fh.Li(fh.A("[ / ]", href="/", cls="text-teal-600")),
                    fh.Li(
                        fh.A("[ .. ]", href=f"{current_path}/..", cls="text-teal-600")
                    ),
                    *[
                        fh.Li(fh.A(p.name, href=f"/{p.repo}", cls="text-teal-600"))
                        for p in [Plan.from_path(r, Path(".")) for r in REPOS]
                    ],
                )
            ),
            fh.Main(*args, cls="flex-1"),
            fh.Footer("PlanMode", cls="text-gray-600 py-2 text-center"),
            cls="min-h-screen flex flex-col",
        ),
    )


def get_section(spec):
    return spec.split(".")[0]


def Add(href: str, spec: str):
    return fh.A(
        "[+]",
        hx_get=f"{href}?spec={spec}",
        hx_target=f"#{slug(href)}-{slug(spec)}",
        hx_swap="beforeend",
        cls="text-green-700",
    )


def Del(href: str, spec):
    return fh.A(
        "[×]",
        hx_delete=f"{href}?spec={spec}",
        hx_target=f"#{slug(href)}-{get_section(spec)}-items",
        hx_confirm="Are you sure?",
        cls="font-bold text-red-800",
    )


@rt("/{repo:str}/{path:path}")
def delete(repo: str, path: Path, spec: str):
    plan = Plan.from_path(repo, path)
    glom.delete(plan, spec)
    plan.write()
    plan = Plan.from_path(repo, path)
    section = plan[get_section(spec)]
    return section.items_to_html()


@rt("/{repo:str}/{path:path}")
def post(repo: str, path: Path, spec: str, name: str):
    plan = Plan.from_path(repo, path)
    section: Section = plan[get_section(spec)]
    parent: Section | Item = glom.glom(plan, spec[: -len(".items")])
    items = parent.items
    print(name)
    items.append(
        Item(parent=parent, name=name, spec=f"{parent.spec}.items.{len(items)}")
    )
    plan.write()
    plan = Plan.from_path(repo, path)
    return section.items_to_html()


@rt("/{repo:str}/{path:path}")
def get(repo: str, path: Path, view: str | None = None, spec: str | None = None):
    plan = Plan.from_path(repo, path)
    if spec is None:
        return render_plan(plan, view)

    section = plan[get_section(spec)]
    return mui.Input(
        name="name",
        type="text",
        placeholder="Press Enter to add...",
        hx_post=f"{plan.href}?spec={spec}",
        hx_target=f"#{slug(plan.href)}-{section.spec}-items",
        hx_trigger="keydown[key=='Enter']",
        cls="px-2 py-1",
    )


def render_plan(plan: Plan, view: str | None = None):
    repo = plan.repo
    path = plan.path

    def PMSubSection(plan: Plan, section_spec: str, index=0):
        section = plan[section_spec]
        sub = [PMSubSection(p, section_spec, index + 1) for p in plan.plans]

        if not any(sub) and not section.items:
            return None

        return mui.Section(
            fh.Header(
                [mui.H3, mui.H4, mui.H5, mui.H6][index](
                    fh.A(plan.name, href=f"{plan.href}?section=plan"),
                    cls="w-full",
                ),
                Add(plan.href, f"{section_spec}.items"),
                cls="flex pt-4 items-end",
            ),
            section.items_to_html(),
            *sub,
        )

    return body(
        mui.H1(plan.name),
        mui.Section(
            fh.Ul(
                *[
                    fh.Li(fh.A(p.name, href=f"/{repo}/{p.path}", cls="text-teal-600"))
                    for p in plan.plans
                ],
                cls="list-none pl-6",
            ),
        ),
        plan.goals.to_html(view),
        *[PMSubSection(p, "goals") for p in plan.plans if view == "goals"],
        plan.status.to_html(view),
        *[PMSubSection(p, "status") for p in plan.plans if view == "status"],
        plan.problems.to_html(view),
        *[PMSubSection(p, "problems") for p in plan.plans if view == "problems"],
        plan.tasks.to_html(view),
        *[PMSubSection(p, "tasks") for p in plan.plans if view == "tasks"],
        current_path=f"/{repo}/{path}",
        current_view=view,
    )


@rt("/")
def get(view: str = ""):
    def Plans(plans: list[Plan]):
        return fh.Ul(
            fh.Li(fh.A(p.name, href=f"/{p.repo}/{p.path}"), Plans(p.plans))
            for p in plans
        )

    def Repo(plan):
        return mui.Section(
            mui.H2(fh.A(plan.name, href=f"/{plan.repo}")), Plans(plan.plans)
        )

    plans = [Plan.from_path(name, Path(".")) for name, path in REPOS.items()]
    return mui.Container(
        mui.H1("PlanMode"),
        *[Repo(plan) for plan in plans],
        current_path="/",
        current_view="",
    )


if __name__ == "__main__":
    fh.serve(port=80)

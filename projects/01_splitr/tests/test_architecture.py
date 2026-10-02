"""Layering rules and the contracts between layers (models, repositories, services)."""

import pytest


def _imports(path):
    """Every module name imported (absolute or relative) by a source file."""
    import ast

    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            names.add(prefix)
            names.update(prefix.rstrip(".") + "." + a.name for a in node.names)
    return names


def _sources(layer):
    from pathlib import Path

    import splitr

    return sorted((Path(splitr.__file__).parent / layer).glob("*.py"))


def _violations(layer, forbidden):
    """Imports in ``layer`` whose module path contains a forbidden word."""
    bad = []
    for path in _sources(layer):
        for name in _imports(path):
            parts = [p for p in name.replace(".", " ").split() if p]
            if any(word in parts for word in forbidden):
                bad.append(f"{layer}/{path.name} imports {name}")
    return bad


def test_models_import_nothing_from_the_app():
    assert _violations("models", {"db", "repositories", "services", "controllers", "flask", "sqlite3"}) == []


def test_repositories_do_not_know_about_services_or_http():
    assert _violations("repositories", {"services", "controllers", "flask"}) == []


def test_services_have_no_http_and_no_sql():
    assert _violations("services", {"controllers", "flask", "sqlite3", "repositories_sql"}) == []
    # Services reach the database only through repositories and db.transaction.
    for path in _sources("services"):
        assert "execute(" not in path.read_text(), f"SQL found in services/{path.name}"


def test_controllers_only_talk_to_services():
    assert _violations("controllers", {"repositories", "db", "sqlite3", "notifier"}) == []
    for path in _sources("controllers"):
        assert "execute(" not in path.read_text(), f"SQL found in controllers/{path.name}"


def test_models_are_immutable_value_objects():
    import dataclasses

    from splitr.models import User

    user = User(id="u1", name="alice")
    assert user.email is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        user.name = "bob"


def test_repository_refuses_unlisted_sort_column(client, group_id):
    from splitr.repositories import expenses as expenses_repo

    with pytest.raises(ValueError):
        expenses_repo.list_for_group(group_id, 10, 0, "id; DROP TABLE expenses")


def test_services_return_models(client, ids, group_id):
    from splitr.models import Balance, Expense, Group, User
    from splitr.services import balances, expenses, groups, users

    assert isinstance(users.get_user(ids["alice"]), User)
    assert isinstance(groups.create_group("x", [ids["alice"]]), Group)
    expense, shares = expenses.add_expense(group_id, ids["alice"], 30)
    assert isinstance(expense, Expense) and expense.id is not None
    assert isinstance(expenses.list_expenses(group_id)[0], Expense)
    assert all(isinstance(b, Balance) for b in balances.get_balances(group_id))

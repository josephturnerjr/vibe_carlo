"""CLI for user management: vibe-carlo-users."""

import argparse
import getpass
import sys

from vibe_carlo.auth import (
    create_user,
    delete_user,
    get_user_by_email,
    list_users,
    update_password,
    verify_password,
)
from vibe_carlo.db import get_connection, init_db


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new user."""
    password = args.password or getpass.getpass("Password: ")
    init_db()
    conn = get_connection()
    try:
        if get_user_by_email(conn, args.email):
            print(f"Error: user '{args.email}' already exists.", file=sys.stderr)
            sys.exit(1)
        create_user(conn, args.email, password)
        print(f"Created user '{args.email.lower()}'.")
    finally:
        conn.close()


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete a user."""
    init_db()
    conn = get_connection()
    try:
        if not delete_user(conn, args.email):
            print(f"Error: user '{args.email}' not found.", file=sys.stderr)
            sys.exit(1)
        print(f"Deleted user '{args.email.lower()}'.")
    finally:
        conn.close()


def cmd_change_password(args: argparse.Namespace) -> None:
    """Change a user's password."""
    password = args.password or getpass.getpass("New password: ")
    init_db()
    conn = get_connection()
    try:
        if not update_password(conn, args.email, password):
            print(f"Error: user '{args.email}' not found.", file=sys.stderr)
            sys.exit(1)
        print(f"Password updated for '{args.email.lower()}'.")
    finally:
        conn.close()


def cmd_list(args: argparse.Namespace) -> None:
    """List all users."""
    init_db()
    conn = get_connection()
    try:
        users = list_users(conn)
    finally:
        conn.close()
    if not users:
        print("No users.")
        return
    for u in users:
        print(f"  {u['email']}  (created {u['created_at']})")


def cmd_assign_snapshots(args: argparse.Namespace) -> None:
    """Assign all unowned snapshots to a user."""
    init_db()
    conn = get_connection()
    try:
        user = get_user_by_email(conn, args.email)
    finally:
        conn.close()
    if user is None:
        print(f"Error: user '{args.email}' not found.", file=sys.stderr)
        sys.exit(1)
        return  # unreachable, but helps type narrowing
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE snapshots SET user_id = ? WHERE user_id IS NULL",
            (user["id"],),
        )
        conn.commit()
        print(f"Assigned {cur.rowcount} snapshot(s) to '{args.email.lower()}'.")
    finally:
        conn.close()


def cmd_check_password(args: argparse.Namespace) -> None:
    """Verify a user's password (for debugging)."""
    password = args.password or getpass.getpass("Password: ")
    init_db()
    conn = get_connection()
    try:
        user = get_user_by_email(conn, args.email)
    finally:
        conn.close()
    if user is None:
        print(f"Error: user '{args.email}' not found.", file=sys.stderr)
        sys.exit(1)
        return  # unreachable, but helps type narrowing
    if verify_password(password, str(user["password_hash"])):
        print("Password is correct.")
    else:
        print("Password is incorrect.")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="vibe-carlo-users",
        description="Manage vibe_carlo users",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a new user")
    p_create.add_argument("email")
    p_create.add_argument("--password", default=None)
    p_create.set_defaults(func=cmd_create)

    p_delete = sub.add_parser("delete", help="Delete a user")
    p_delete.add_argument("email")
    p_delete.set_defaults(func=cmd_delete)

    p_passwd = sub.add_parser("change-password", help="Change a user's password")
    p_passwd.add_argument("email")
    p_passwd.add_argument("--password", default=None)
    p_passwd.set_defaults(func=cmd_change_password)

    p_list = sub.add_parser("list", help="List all users")
    p_list.set_defaults(func=cmd_list)

    p_assign = sub.add_parser("assign-snapshots", help="Assign unowned snapshots to a user")
    p_assign.add_argument("email")
    p_assign.set_defaults(func=cmd_assign_snapshots)

    p_check = sub.add_parser("check-password", help="Verify a user's password")
    p_check.add_argument("email")
    p_check.add_argument("--password", default=None)
    p_check.set_defaults(func=cmd_check_password)

    return parser


def main() -> None:
    """Entry point for vibe-carlo-users CLI."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)

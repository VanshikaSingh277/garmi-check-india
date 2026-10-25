"""Org and first-admin setup, from the command line only (spec §5.10): orgs are never created over HTTP.

Usage (from apps/api):
  python -m app.admin create-org --name "Jaipur ASHA network" --type health_dept --state Rajasthan [--district-id ID]
  python -m app.admin invite-admin --org ORG_ID --name "Asha Devi" --phone +91XXXXXXXXXX
The admin then signs in with an OTP (purpose worker_login) and invites workers through the API."""
import argparse
import sys

from sqlalchemy import select

from . import db, secure
from .models import Org, Worker

TYPES = ("health_dept", "ngo", "rwa", "school", "other")


def create_org(name: str, type_: str, state: str | None, district_id: str | None) -> str:
    if type_ not in TYPES:
        raise SystemExit(f"--type must be one of {', '.join(TYPES)}")
    with db.session() as s:
        o = Org(name=name, type=type_, state=state, district_id=district_id)
        s.add(o)
        s.flush()
        return o.id


def invite_admin(org_id: str, name: str, phone_raw: str) -> str:
    phone = secure.normalise_phone(phone_raw)
    if not phone:
        raise SystemExit("--phone must be an Indian mobile number (+91)")
    with db.session() as s:
        if not s.get(Org, org_id):
            raise SystemExit("no such org")
        ph = secure.phone_hmac(phone)
        if s.scalars(select(Worker).where(Worker.phone_hmac == ph)).first():
            raise SystemExit("this number is already a worker")
        enc, kid = secure.encrypt_phone(phone)
        w = Worker(org_id=org_id, role="org_admin", display_name=name, phone_enc=enc, key_id=kid, phone_hmac=ph)
        s.add(w)
        s.flush()
        return w.id


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m app.admin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-org")
    a.add_argument("--name", required=True)
    a.add_argument("--type", required=True, choices=TYPES)
    a.add_argument("--state")
    a.add_argument("--district-id")
    b = sub.add_parser("invite-admin")
    b.add_argument("--org", required=True)
    b.add_argument("--name", required=True)
    b.add_argument("--phone", required=True)
    args = ap.parse_args(argv)
    db.migrate()
    if args.cmd == "create-org":
        print("org", create_org(args.name, args.type, args.state, args.district_id))
    else:
        print("org_admin", invite_admin(args.org, args.name, args.phone), "(number ending", args.phone[-2:] + ")")


if __name__ == "__main__":
    sys.exit(main())

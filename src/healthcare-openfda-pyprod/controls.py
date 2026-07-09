import argparse
import sys
import json
from intersystems_pyprod import director


def cmd_start(args):
    """Start a production."""
    status = director.start_production(args.production)
    print(f"Start status: {status}")
    return 0 if str(status) == "1" else 1


def cmd_stop(args):
    """Stop the running production."""
    status = director.stop_production(timeout=args.timeout, force=args.force)
    print(f"Stop status: {status}")
    return 0 if str(status) == "1" else 1


def cmd_restart(args):
    """Restart the running production."""
    status = director.restart_production(timeout=args.timeout, force=args.force)
    print(f"Restart status: {status}")
    return 0 if str(status) == "1" else 1


def cmd_status(args):
    """Get production status."""
    status, prod_name, state = director.get_production_status(
        lock_timeout=args.timeout,
        skip_lock_if_running=args.skip_lock
    )

    state_map = {
        "1": "Running",
        "2": "Stopped",
        "3": "Suspended",
        "4": "Troubled"
    }

    print(f"Status: {status}")
    print(f"Production: {prod_name if prod_name else 'None'}")
    print(f"State: {state_map.get(str(state), f'Unknown ({state})')}")
    return 0 if str(status) == "1" else 1


def cmd_clean(args):
    """Clean production (development only)."""
    if not args.confirm:
        print("WARNING: This will remove all messages and production data!")
        print("Use --confirm to proceed")
        return 1

    status = director.clean_production(kill_app_data_too=args.kill_data)
    print(f"Clean status: {status}")
    return 0 if str(status) == "1" else 1


def cmd_update(args):
    """Update the running production."""
    status = director.update_production(
        timeout=args.timeout,
        force=args.force,
        called_by_schedule_handler=False
    )
    print(f"Update status: {status}")
    return 0 if str(status) == "1" else 1


def cmd_enable(args):
    """Enable or disable a config item."""
    status = director.enable_config_item(
        config_item_name=args.item,
        enable=args.enable,
        do_update=not args.no_update
    )
    action = "enabled" if args.enable else "disabled"
    print(f"Config item '{args.item}' {action}: {status}")
    return 0 if str(status) == "1" else 1


def cmd_list(args):
    """List all productions."""
    status, prod_list, prod_details = director.list_all_productions()

    if args.json:
        print(json.dumps(prod_details, indent=2))
    else:
        print(f"Found {len(prod_list)} production(s):\n")
        for prod_name in prod_list:
            details = prod_details.get(prod_name, {})
            print(f"  {prod_name}")
            print(f"    Status: {details.get('status', 'Unknown')}")
            print(f"    Last started: {details.get('last_start_time', 'N/A')}")
            print(f"    Last stopped: {details.get('last_stop_time', 'N/A')}")
            print()

    return 0 if str(status) == "1" else 1


def cmd_messages(args):
    """Get messages for a host."""
    messages = director.get_host_messages(args.host, max_results=args.limit)

    if args.json:
        print(json.dumps(messages, indent=2))
    else:
        print(f"Found {len(messages)} message(s) for '{args.host}':\n")
        for msg in messages:
            print(f"  ID: {msg['id']} | Time: {msg['time_created']}")
            print(f"    {msg['source']} -> {msg['target']}")
            print(f"    Status: {msg['status']} | Session: {msg['session_id']}")
            print(f"    Body: {msg['body_class']} (ID: {msg['body_id']})")
            print()

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Control InterSystems IRIS Productions from the command line"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    subparsers.required = True

    # start command
    start_parser = subparsers.add_parser("start", help="Start a production")
    start_parser.add_argument("production", nargs="?", help="Production class name (e.g., MyPackage.MyProduction)")
    start_parser.set_defaults(func=cmd_start)

    # stop command
    stop_parser = subparsers.add_parser("stop", help="Stop the running production")
    stop_parser.add_argument("--timeout", type=int, default=10, help="Timeout in seconds (default: 10)")
    stop_parser.add_argument("--force", action="store_true", help="Force kill jobs that won't stop")
    stop_parser.set_defaults(func=cmd_stop)

    # restart command
    restart_parser = subparsers.add_parser("restart", help="Restart the running production")
    restart_parser.add_argument("--timeout", type=int, default=10, help="Timeout in seconds (default: 10)")
    restart_parser.add_argument("--force", action="store_true", help="Force kill jobs that won't stop")
    restart_parser.set_defaults(func=cmd_restart)

    # status command
    status_parser = subparsers.add_parser("status", help="Get production status")
    status_parser.add_argument("--timeout", type=int, default=10, help="Lock timeout in seconds (default: 10)")
    status_parser.add_argument("--skip-lock", action="store_true", help="Skip lock if running")
    status_parser.set_defaults(func=cmd_status)

    # clean command
    clean_parser = subparsers.add_parser("clean", help="Clean production (DEVELOPMENT ONLY)")
    clean_parser.add_argument("--confirm", action="store_true", help="Confirm the clean operation")
    clean_parser.add_argument("--kill-data", action="store_true", help="Also remove application data")
    clean_parser.set_defaults(func=cmd_clean)

    # update command
    update_parser = subparsers.add_parser("update", help="Update the running production")
    update_parser.add_argument("--timeout", type=int, default=10, help="Timeout in seconds (default: 10)")
    update_parser.add_argument("--force", action="store_true", help="Force kill jobs that won't stop")
    update_parser.set_defaults(func=cmd_update)

    # enable/disable command
    enable_parser = subparsers.add_parser("enable", help="Enable a config item")
    enable_parser.add_argument("item", help="Config item name")
    enable_parser.add_argument("--enable", type=lambda x: x.lower() != "false", default=True,
                               help="Enable (true) or disable (false)")
    enable_parser.add_argument("--no-update", action="store_true", help="Don't update production after change")
    enable_parser.set_defaults(func=cmd_enable)

    disable_parser = subparsers.add_parser("disable", help="Disable a config item")
    disable_parser.add_argument("item", help="Config item name")
    disable_parser.add_argument("--no-update", action="store_true", help="Don't update production after change")
    disable_parser.set_defaults(func=lambda args: cmd_enable(argparse.Namespace(**{**vars(args), 'enable': False})))

    # list command
    list_parser = subparsers.add_parser("list", help="List all productions")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.set_defaults(func=cmd_list)

    # messages command
    messages_parser = subparsers.add_parser("messages", help="Get messages for a host")
    messages_parser.add_argument("host", help="Host/config item name")
    messages_parser.add_argument("--limit", type=int, default=100, help="Maximum number of messages (default: 100)")
    messages_parser.add_argument("--json", action="store_true", help="Output as JSON")
    messages_parser.set_defaults(func=cmd_messages)

    args = parser.parse_args()

    try:
        return args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

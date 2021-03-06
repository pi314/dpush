import argparse
import sys

from . import lib_config
from . import cli_d
from . import cli_tq


def main():
    parser = argparse.ArgumentParser(prog='dpush',
            description='A Task Queue with Built-in Wrapper to drive')
    parser.set_defaults(block=False)

    subparsers = parser.add_subparsers(title='subcommands')

    parser_d = subparsers.add_parser('d', help='d mode - Wrapper to drive')
    parser_d.set_defaults(mode='d')
    parser_d.set_defaults(dump=False)
    parser_d.set_defaults(subcmd=cli_d.main)

    parser_d.add_argument('cmd', nargs=argparse.REMAINDER,
            help='drive/d command')


    parser_tq = subparsers.add_parser('tq', help='tq mode - Built-in task queue')
    parser_tq.set_defaults(mode='tq')
    parser_tq.set_defaults(subcmd=cli_tq.main)
    parser_tq.set_defaults(auto_quit=None)

    parser_tq.add_argument('-b', '--block', action='store_true', dest='block',
            help='block and wait instead of put task into queue')

    parser_tq.add_argument('-t', '--telegram', action='store_true', dest='telegram',
            help='enable telegram notification (configuration persists)')

    parser_tq.set_defaults(telegram=None)
    parser_tq.add_argument('-T', '--no-telegram', action='store_false', dest='telegram',
            help='disable telegram notification (configuration persists)')

    parser_tq.add_argument('-l', '--load', action='store_true', dest='load',
            help='load unfinished tasks from tq.log')

    parser_tq.add_argument('-n', '--dry', action='store_true', dest='dry',
            help='show actions and finish without actually running')

    parser_tq.add_argument('-d', '--dump', action='store_true', dest='dump',
            help='show current content of task queue')

    parser_tq.add_argument('-a', '--auto-quit', nargs='?', const='?', dest='auto_quit',
            help='enable auto-quit (quit when queue is empty after provided time, set 0 to disable)')

    parser_tq.add_argument('cmd', nargs=argparse.REMAINDER,
            help='shell command to be queued into tq')

    args = parser.parse_args()

    lib_config.load()

    return args.subcmd(args)

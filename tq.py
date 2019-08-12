import sys

from . import config
from . import server
from . import client
from . import telegram
from . import logger


def main(args):
    if args.telegram is not None:
        config.set('telegram', 'enable', args.telegram)
        config.save()

    if args.telegram:
        try:
            telegram.enable()
        except KeyboardInterrupt:
            exit(1)
        config.save()

    if args.load:
        return server.load(args.dry)

    if args.dump or (len(args.cmd) and args.cmd[0] == 'dump'):
        return client.request_dump()

    if not len(args.cmd):
        return server.start()

    if len(args.cmd) and args.cmd[0] == 'd':
        logger.log_error('Use sub-command "d" instead')
        return 1

    return client.submit_task(args)
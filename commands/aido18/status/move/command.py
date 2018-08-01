from dt_shell import DTCommandAbs

class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell, args):
        print 'This is move with args %r' % args

    @staticmethod
    def complete():
        return ['cane', 'gatto']

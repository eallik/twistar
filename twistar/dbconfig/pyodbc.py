from twistar.dbconfig.base import InteractionBase


class PyODBCDBConfig(InteractionBase):

    def whereToString(self, where):
        assert(isinstance(where, list))  # XXX: what it a tuple is passed? with duck typing, it would work
        query = where[0]  # ? will be correct
        args = where[1:]
        return (query, args)

    def updateArgsToString(self, args):
        colnames = self.escapeColNames(args.keys())
        setstring = ",".join([key + " = ?" for key in colnames])
        return (setstring, args.values())

    def insertArgsToString(self, vals):
        return "(" + ",".join(["?" for _ in vals.items()]) + ")"

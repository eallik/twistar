from twisted.python import log

from twistdb.dbconfig import Registry        
from twistdb.exceptions import EmtpyOrImaginaryTableError

class DBConfig:
    LOG = False
    
    def __init__(self, dbapi):
        self.dbapi = dbapi


    def log(self, query, args, kwargs):
        if not DBConfig.LOG:
            return
        log.msg("TWISTDB query: %s" % query)
        if len(args) > 0:
            log.msg("TWISTDB args: %s" % ",".join(map(lambda x: str(x), *args)))
        elif len(kwargs) > 0:
            log.msg("TWISTDB kargs: %s" % str(kwargs))        


    def execute(self, query, *args, **kwargs):
        #print query, args
        self.log(query, args, kwargs)
        return Registry.DBPOOL.runQuery(query, *args, **kwargs)


    def executeTxn(self, txn, query, *args, **kwargs):
        #print query, args
        self.log(query, args, kwargs)
        return txn.execute(query, *args, **kwargs)


    def select(self, klass, id=None, where=None, group=None, limit=None, tablename=None):
        tablename = tablename or klass.tablename()
        one = False
        
        if id is not None:
            where = ["id = ?", id]
            one = True
        if limit is not None and int(limit) == 1:
            one = True
            
        q = "SELECT * FROM %s" % tablename
        args = []
        if where is not None:
            wherestr, args = self.whereToString(where)
            q += " WHERE " + wherestr
        if group is not None:
            q += " GROUP BY " + group
        if limit is not None:
            q += " LIMIT " + str(limit)
        return Registry.DBPOOL.runInteraction(self._doselect, klass, q, args, one)


    ## Convert {'name': value} to "%s,%s,%s"
    def insertArgsToString(self, vals):
        return ",".join(["%s" for _ in vals.items()])        


    ## Vals should be in form of {'name': value, 'othername': value}
    ## This func should return id of new row
    def insert(self, tablename, vals, txn):
        params = self.insertArgsToString(vals)
        colnames = ",".join(vals.keys())
        q = "INSERT INTO %s (%s) " % (tablename, colnames)
        q += "VALUES(" + params + ")"
        self.executeTxn(txn, q, vals.values())
        return self.getLastInsertID(txn)


    def getLastInsertID(self, txn):
        q = "SELECT LAST_INSERT_ID()"
        self.executeTxn(txn, q)            
        result = txn.fetchall()
        return result[0][0]
    

    def delete(self, klass, where=None):
        q = "DELETE FROM %s" % klass.tablename()
        args = []
        if where is not None:
            wherestr, args = self.whereToString(where)
            q += " WHERE " + wherestr
        return self.execute(q, args)


    ## Args should be in form of {'name': value, 'othername': value}
    def update(self, tablename, args, where=None, txn=None):
        setstring, args = self.updateArgsToString(args)
        q = "UPDATE %s " % tablename + " SET " + setstring
        if where is not None:
            wherestr, whereargs = self.whereToString(where)
            q += " WHERE " + wherestr
            args += whereargs
            
        if txn is not None:
            return self.executeTxn(txn, q, args)
        return self.execute(q, args)


    # Values is a row from a db, this method will create a hash with
    # key => value of colname => value based on the table description
    def valuesToHash(self, klass, txn, values):
        cols = self.getSchema(klass.tablename(), txn)
        h = {}
        for index in range(len(values)):
            colname = cols[index]
            h[colname] = values[index]
        return h


    def _doselect(self, txn, klass, q, args, one=False):
        self.executeTxn(txn, q, args)

        if one:
            result = txn.fetchone()
            if not result:
                return None
            vals = self.valuesToHash(klass, txn, result)
            return klass(**vals)

        results = []
        for result in txn.fetchall():
            vals = self.valuesToHash(klass, txn, result)
            results.append(klass(**vals))            
        return results    


    def getSchema(self, tablename, txn=None):
        if not Registry.SCHEMAS.has_key(tablename) and txn is not None:
            self.executeTxn(txn, "DESCRIBE %s" % tablename)
            Registry.SCHEMAS[tablename] = [row[0] for row in txn.fetchall()]
        return Registry.SCHEMAS.get(tablename, [])
            

    def insertObj(self, obj):
        def _doinsert(txn):
            klass = obj.__class__
            tablename = klass.tablename()
            cols = self.getSchema(tablename, txn)
            if len(cols) == 0:
                raise EmtpyOrImaginaryTableError, "Table %s empty or imaginary." % tablename
            vals = obj.toHash(cols, includeBlank=True, exclude=['id'])
            obj.id = self.insert(tablename, vals, txn)
            return obj
        return Registry.DBPOOL.runInteraction(_doinsert)


    def updateObj(self, obj):
        def _doupdate(txn):
            klass = obj.__class__
            tablename = klass.tablename()
            cols = self.getSchema(tablename, txn)
            
            vals = obj.toHash(cols, exclude=['id'])
            return self.update(tablename, vals, where=['id = ?', obj.id], txn=txn)
        # We don't want to return the cursor - so add a blank callback returning the obj
        return Registry.DBPOOL.runInteraction(_doupdate).addCallback(lambda _: obj)    


    def refreshObj(self, obj):
        def _dorefreshObj(newobj):
            if obj is None:
                raise CannotRefreshError, "Can't refresh if id not longer exists."
            tablename = obj.tablename()
            for key in self.getSchema(tablename):
                setattr(obj, key, getattr(newobj, key))
        return self.select(obj.__class__, obj.id).addCallback(_dorefreshObj)


    def whereToString(self, where):
        assert(type(where) is list)
        query = where[0].replace("?", "%s")
        args = where[1:]
        return (query, args)


    ## Args should be in form of {'name': value, 'othername': value}
    ## Convert to form 'name = %s, othername = %s, ...'
    def updateArgsToString(self, args):
        setstring = ",".join([key + " = %s" for key in args.keys()])
        return (setstring, args.values())

# Use PyMySQL (pure Python, easy to install on Windows) as the MySQL driver for Django.
import pymysql

pymysql.version_info = (2, 2, 1, "final", 0)  # Django checks the driver version number
pymysql.install_as_MySQLdb()

# import os
# from mysql.connector import pooling
# from dotenv import load_dotenv

# load_dotenv()

# DB_CONFIG = {
#     "host": os.getenv("DB_HOST", "localhost"),
#     "user": os.getenv("DB_USER", "root"),
#     "password": os.getenv("DB_PASSWORD", ""),
#     "database": os.getenv("DB_NAME", "expense_tracker"),
#     "port": int(os.getenv("DB_PORT", "3306")),
# }

# pool = pooling.MySQLConnectionPool(
#     pool_name="expense_pool",
#     pool_size=5,
#     pool_reset_session=True,
#     **DB_CONFIG
# )

# def get_conn():
#     return pool.get_connection()
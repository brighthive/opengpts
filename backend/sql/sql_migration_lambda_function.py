import os
import psycopg2
from psycopg2 import sql

def run_migrations():
    # Database connection parameters
    db_params = {
        "host": os.environ['POSTGRES_HOST'],
        "port": os.environ['POSTGRES_PORT'],
        "dbname": os.environ['POSTGRES_DB'],
        "user": os.environ['POSTGRES_USER'],
        "password": os.environ['POSTGRES_PASSWORD']
    }

    # Establish a connection to the database
    conn = psycopg2.connect(**db_params)
    conn.autocommit = True
    cursor = conn.cursor()

    # Path to the migration scripts
    migrations_path = '/migrations'

    # Execute each migration script in the migrations directory
    for root, dirs, files in os.walk(migrations_path):
        for filename in sorted(files):
            if filename.endswith('.sql'):
                file_path = os.path.join(root, filename)
                with open(file_path, 'r') as file:
                    sql_script = file.read()
                    cursor.execute(sql.SQL(sql_script))

    cursor.close()
    conn.close()

def lambda_handler(event, context):
    try:
        run_migrations()
        return {
            'statusCode': 200,
            'body': 'Migrations executed successfully.'
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Error executing migrations: {str(e)}'
        }

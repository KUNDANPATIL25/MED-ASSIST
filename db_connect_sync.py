import os
import pandas as pd
import psycopg2
from psycopg2 import sql, pool
from dotenv import load_dotenv
from typing import Dict, Optional, List
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL_SYNC")  # Example: "postgresql://user:password@host:port/dbname"

# Connection pool configuration
MIN_CONNECTIONS = 5
MAX_CONNECTIONS = 20

# Create a connection pool
connection_pool = None

def init_connection_pool():
    """Initialize the connection pool if it doesn't exist."""
    global connection_pool
    if connection_pool is None:
        try:
            connection_pool = pool.ThreadedConnectionPool(
                MIN_CONNECTIONS, 
                MAX_CONNECTIONS,
                DATABASE_URL,
                # Set some connection parameters
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            logger.info(f"Connection pool initialized with {MIN_CONNECTIONS}-{MAX_CONNECTIONS} connections")
        except Exception as e:
            logger.error(f"Error initializing connection pool: {e}")
            raise

# Initialize the connection pool
init_connection_pool()

def get_connection():
    """Get a connection from the pool."""
    if connection_pool is None:
        init_connection_pool()
    
    conn = connection_pool.getconn()
    try:
        # Set statement timeout
        with conn.cursor() as cursor:
            cursor.execute("SET statement_timeout = 30000")
        return conn
    except Exception as e:
        connection_pool.putconn(conn)
        logger.error(f"Error setting up connection: {e}")
        raise

def return_connection(conn):
    """Return a connection to the pool."""
    if connection_pool and conn:
        connection_pool.putconn(conn)

def execute_query(query: str, parameters: Optional[Dict] = None, retries: int = 3):
    """
    Executes a write operation such as INSERT, UPDATE, or DELETE with retry logic.

    :param query: The SQL query string to execute.
    :param parameters: Optional parameters for the SQL query.
    :param retries: Number of retry attempts for transient errors.
    """
    conn = None
    retry_count = 0
    
    while retry_count < retries:
        try:
            conn = get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL(query), parameters or ())
                conn.commit()
                logger.debug("Operation successful.")
                return cursor.rowcount  # Return number of affected rows
        except psycopg2.OperationalError as e:
            # Handle connection issues
            logger.warning(f"Operational error on attempt {retry_count + 1}: {e}")
            if conn:
                conn.rollback()
            retry_count += 1
            # Add exponential backoff
            time.sleep(0.5 * (2 ** retry_count))
        except Exception as e:
            # Handle other errors
            logger.error(f"Error executing query: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                return_connection(conn)
    
    # If we get here, we've exhausted retries
    raise Exception(f"Failed to execute query after {retries} retries")

def fetch_results(query: str, parameters: Optional[Dict] = None) -> List[Dict]:
    """
    Executes a read operation and returns the result as a list of dictionaries.

    :param query: The SQL query string to execute.
    :param parameters: Optional parameters for the SQL query.
    :return: A list of dictionaries representing the query results.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL(query), parameters or ())
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching results: {e}")
        return []
    finally:
        if conn:
            return_connection(conn)

def fetch_dataframe(query: str, parameters: Optional[Dict] = None) -> pd.DataFrame:
    """
    Executes a read operation and returns the result as a Pandas DataFrame.

    :param query: The SQL query string to execute.
    :param parameters: Optional parameters for the SQL query.
    :return: A Pandas DataFrame with the query results.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL(query), parameters or ())
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(rows, columns=columns)
            return df
    except Exception as e:
        logger.error(f"Error fetching DataFrame: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            return_connection(conn)

def batch_execute(queries_with_params: List[Dict[str, any]]):
    """
    Execute multiple operations in a single transaction.
    
    :param queries_with_params: List of dictionaries with 'query' and 'params' keys.
    :return: None
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            for item in queries_with_params:
                query = item.get('query')
                params = item.get('params', {})
                cursor.execute(sql.SQL(query), params or ())
            conn.commit()
            logger.debug("Batch operation committed successfully")
    except Exception as e:
        logger.error(f"Error executing batch operation: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            return_connection(conn)

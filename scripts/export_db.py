#!/usr/bin/env python3
"""
Database Export Script for YouTube Research Project

This script exports the PostgreSQL database to various formats for remote analysis.
It can be run on the host machine outside of Docker containers.

Usage:
    python export_db.py --format csv --output exports/
    python export_db.py --format json --tables videos,sessions
    python export_db.py --format sql --output backup.sql
"""

import argparse
import os
import sys
import json
import csv
from datetime import datetime
from pathlib import Path
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DatabaseExporter:
    def __init__(self, host='localhost', port=5432, database=None, user=None, password=None):
        self.host = host
        self.port = port
        self.database = database or os.getenv('POSTGRES_DB', 'youtube_research')
        self.user = user or os.getenv('POSTGRES_USER', 'yt_user')
        self.password = password or os.getenv('POSTGRES_PASSWORD')
        
        if not self.password:
            raise ValueError("Database password not found. Set POSTGRES_PASSWORD in .env or pass as argument")
    
    def connect(self):
        """Establish database connection"""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            return conn
        except psycopg2.Error as e:
            print(f"Error connecting to database: {e}")
            sys.exit(1)
    
    def get_table_names(self):
        """Get all table names from the database"""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                """)
                return [row[0] for row in cur.fetchall()]
    
    def export_to_csv(self, output_dir, tables=None):
        """Export tables to CSV files"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        tables = tables or self.get_table_names()
        
        with self.connect() as conn:
            for table in tables:
                print(f"Exporting {table} to CSV...")
                
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    # First get column names from the table schema
                    cur.execute("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = %s 
                        ORDER BY ordinal_position
                    """, (table,))
                    column_names = [row[0] for row in cur.fetchall()]
                    
                    # Now get the actual data
                    cur.execute(f"SELECT * FROM {table}")
                    rows = cur.fetchall()
                    
                    if not rows:
                        print(f"  Warning: {table} is empty")
                        continue
                    
                    csv_file = output_path / f"{table}.csv"
                    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=column_names)
                        writer.writeheader()
                        for row in rows:
                            # Convert any non-serializable types to strings
                            clean_row = {}
                            for key in column_names:
                                value = row.get(key)
                                if isinstance(value, (list, dict)):
                                    clean_row[key] = json.dumps(value)
                                else:
                                    clean_row[key] = value
                            writer.writerow(clean_row)
                    
                    print(f"  Exported {len(rows)} rows to {csv_file}")
    
    def export_to_json(self, output_file, tables=None):
        """Export tables to JSON file"""
        tables = tables or self.get_table_names()
        data = {}
        
        with self.connect() as conn:
            for table in tables:
                print(f"Exporting {table} to JSON...")
                
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(f"SELECT * FROM {table}")
                    rows = cur.fetchall()
                    
                    # Convert to JSON-serializable format
                    json_rows = []
                    for row in rows:
                        json_row = {}
                        for key, value in row.items():
                            if isinstance(value, datetime):
                                json_row[key] = value.isoformat()
                            else:
                                json_row[key] = value
                        json_rows.append(json_row)
                    
                    data[table] = json_rows
                    print(f"  Exported {len(rows)} rows from {table}")
        
        # Write to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"JSON export completed: {output_path}")
    
    def export_to_sql(self, output_file, tables=None):
        """Export database schema and data to SQL file"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use pg_dump for complete SQL export
        cmd = [
            'pg_dump',
            f'--host={self.host}',
            f'--port={self.port}',
            f'--username={self.user}',
            f'--dbname={self.database}',
            '--no-password',
            '--verbose',
            '--clean',
            '--if-exists',
            '--create'
        ]
        
        if tables:
            for table in tables:
                cmd.extend(['--table', table])
        
        # Set password via environment variable
        env = os.environ.copy()
        env['PGPASSWORD'] = self.password
        
        try:
            import subprocess
            with open(output_path, 'w') as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, 
                                      env=env, text=True, check=True)
            print(f"SQL export completed: {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error running pg_dump: {e.stderr}")
            print("Make sure pg_dump is installed and accessible in PATH")
            sys.exit(1)
        except FileNotFoundError:
            print("pg_dump not found. Please install PostgreSQL client tools.")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Export YouTube Research Database')
    parser.add_argument('--format', choices=['csv', 'json', 'sql'], required=True,
                       help='Export format')
    parser.add_argument('--output', required=True,
                       help='Output file or directory')
    parser.add_argument('--tables', 
                       help='Comma-separated list of tables to export (default: all)')
    parser.add_argument('--host', default='localhost',
                       help='Database host (default: localhost)')
    parser.add_argument('--port', type=int, default=5432,
                       help='Database port (default: 5432)')
    parser.add_argument('--database',
                       help='Database name (default: from .env)')
    parser.add_argument('--user',
                       help='Database user (default: from .env)')
    parser.add_argument('--password',
                       help='Database password (default: from .env)')
    
    args = parser.parse_args()
    
    # Parse tables list
    tables = None
    if args.tables:
        tables = [t.strip() for t in args.tables.split(',')]
    
    # Create exporter
    try:
        exporter = DatabaseExporter(
            host=args.host,
            port=args.port,
            database=args.database,
            user=args.user,
            password=args.password
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Perform export
    print(f"Starting {args.format.upper()} export...")
    print(f"Database: {exporter.database}@{exporter.host}:{exporter.port}")
    
    if args.format == 'csv':
        exporter.export_to_csv(args.output, tables)
    elif args.format == 'json':
        exporter.export_to_json(args.output, tables)
    elif args.format == 'sql':
        exporter.export_to_sql(args.output, tables)
    
    print("Export completed successfully!")

if __name__ == '__main__':
    main()
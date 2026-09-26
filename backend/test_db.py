import psycopg
try:
    conn = psycopg.connect("postgresql://postgres:postgrespassword@localhost:5432/doc_intelligence")
    print("Connected successfully!")
    conn.close()
except Exception as e:
    print("Failed with postgrespassword:", str(e))
    try:
        conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/doc_intelligence")
        print("Connected successfully with postgres:postgres!")
        conn.close()
    except Exception as e2:
        print("Failed with postgres:", str(e2))

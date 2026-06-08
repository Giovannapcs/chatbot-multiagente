import psycopg2
import json
from psycopg2 import sql

# ========================================
# CONFIGURAÇÃO - PREENCHA COM OS DADOS DO NOVO BANCO
# ========================================
DB_CONFIG = {
    "host": "zbx-database.c302q84iqlq0.us-east-2.rds.amazonaws.com",
    "port": 5432,
    "database": "zabbix",
    "user": "neo4j_reader",
    "password": "QSuXPa=*%2fQU[?m"
}

def listar_tabelas(cursor):
    """Lista todas as tabelas do banco"""
    cursor.execute("""
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name;
    """)
    return cursor.fetchall()

def listar_colunas(cursor, schema, table):
    """Lista todas as colunas de uma tabela"""
    cursor.execute("""
        SELECT 
            column_name, 
            data_type, 
            is_nullable,
            column_default
        FROM information_schema.columns 
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position;
    """, (schema, table))
    return cursor.fetchall()

def contar_registros(cursor, schema, table):
    """Conta registros em uma tabela"""
    try:
        query = sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
            sql.Identifier(schema),
            sql.Identifier(table)
        )
        cursor.execute(query)
        return cursor.fetchone()[0]
    except Exception as e:
        return f"Erro: {str(e)}"

def amostra_dados(cursor, schema, table, limit=5):
    """Pega uma amostra de dados da tabela"""
    try:
        query = sql.SQL("SELECT * FROM {}.{} LIMIT %s").format(
            sql.Identifier(schema),
            sql.Identifier(table)
        )
        cursor.execute(query, (limit,))
        colunas = [desc[0] for desc in cursor.description]
        registros = cursor.fetchall()
        return {
            "colunas": colunas,
            "registros": [dict(zip(colunas, reg)) for reg in registros]
        }
    except Exception as e:
        return {"erro": str(e)}

def main():
    print("DESCOBRINDO SCHEMA DO POSTGRESQL\n")
    
    try:
        # Conecta no banco
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print(" Conexão estabelecida com sucesso!\n")
        
        # Lista tabelas
        tabelas = listar_tabelas(cursor)
        print(f" Total de tabelas encontradas: {len(tabelas)}\n")
        
        resultado = {
            "banco": DB_CONFIG["database"],
            "total_tabelas": len(tabelas),
            "tabelas": {}
        }
        
        # Para cada tabela, descobre estrutura
        for schema, table in tabelas:
            nome_completo = f"{schema}.{table}"
            print(f"📋 Analisando: {nome_completo}")
            
            # Colunas
            colunas = listar_colunas(cursor, schema, table)
            
            # Total de registros
            total_regs = contar_registros(cursor, schema, table)
            print(f"   └─ Registros: {total_regs}")
            
            # Amostra
            amostra = amostra_dados(cursor, schema, table, 3)
            
            resultado["tabelas"][nome_completo] = {
                "schema": schema,
                "tabela": table,
                "total_registros": total_regs,
                "colunas": [
                    {
                        "nome": col[0],
                        "tipo": col[1],
                        "nullable": col[2],
                        "default": col[3]
                    }
                    for col in colunas
                ],
                "amostra": amostra
            }
        
        cursor.close()
        conn.close()
        
        # Salva resultado em JSON
        with open("schema_descoberto.json", "w", encoding="utf-8") as f:
            json.dump(resultado, indent=2, ensure_ascii=False, default=str, fp=f)
        
        print("\n Análise completa!")
        print(" Resultado salvo em: schema_descoberto.json")
        
        # Mostra resumo
        print("\n" + "="*60)
        print("RESUMO DAS TABELAS")
        print("="*60)
        for nome, info in resultado["tabelas"].items():
            print(f"\n{nome}")
            print(f"  Colunas: {len(info['colunas'])}")
            print(f"  Registros: {info['total_registros']}")
            if info['colunas']:
                print(f"  Principais campos: {', '.join([c['nome'] for c in info['colunas'][:5]])}")
        
    except Exception as e:
        print(f"Erro: {str(e)}")

if __name__ == "__main__":
    main()

"""
====================================================
 Actualizar movies.db con datos de IMDb 2022+
====================================================
Coloca este script en la misma carpeta que:
  - movies.db
  - title.basics.tsv.gz
  - title.ratings.tsv.gz

Luego corre: python update_movies_db.py
"""

import sqlite3
import pandas as pd

DB_PATH      = "movies.db"
BASICS_PATH  = "title.basics.tsv.gz"
RATINGS_PATH = "title.ratings.tsv.gz"
FROM_YEAR    = 2022   # Solo películas de este año en adelante


print("=" * 55)
print("PASO 1 — Leyendo title.basics.tsv.gz ...")
print("=" * 55)

basics = pd.read_csv(
    BASICS_PATH,
    sep='\t',
    compression='gzip',
    low_memory=False,
    na_values='\\N',
    usecols=['tconst', 'titleType', 'primaryTitle', 'startYear']
)

# Solo películas (no series, shorts, etc.)
movies = basics[basics['titleType'] == 'movie'][['tconst', 'primaryTitle', 'startYear']].copy()
movies = movies[movies['startYear'] >= FROM_YEAR].copy()
movies['startYear'] = movies['startYear'].astype('Int64')
print(f"✅ Películas {FROM_YEAR}+: {len(movies):,}")


print("\n" + "=" * 55)
print("PASO 2 — Leyendo title.ratings.tsv.gz ...")
print("=" * 55)

ratings = pd.read_csv(
    RATINGS_PATH,
    sep='\t',
    compression='gzip',
    low_memory=False,
    na_values='\\N'
)
print(f"✅ Ratings disponibles: {len(ratings):,}")


print("\n" + "=" * 55)
print("PASO 3 — Cruzando películas con ratings ...")
print("=" * 55)

merged = movies.merge(ratings, on='tconst', how='inner')
merged = merged.dropna(subset=['primaryTitle', 'startYear', 'averageRating'])
merged = merged[merged['numVotes'] >= 10]  # Filtrar muy desconocidas
print(f"✅ Películas {FROM_YEAR}+ con rating: {len(merged):,}")

# Ver los mejores ejemplos
print("\nTop 10 por votos:")
print(merged.sort_values('numVotes', ascending=False)[
    ['primaryTitle', 'startYear', 'averageRating', 'numVotes']
].head(10).to_string(index=False))


print("\n" + "=" * 55)
print("PASO 4 — Conectando a movies.db ...")
print("=" * 55)

conn   = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Ver estado actual
current = cursor.execute("SELECT COUNT(*), MAX(year) FROM movies").fetchone()
print(f"Estado actual: {current[0]:,} películas | último año: {current[1]}")

# Ver el MAX id actual para continuar desde ahí
max_id = cursor.execute("SELECT MAX(id) FROM movies").fetchone()[0]
print(f"MAX id actual en movies: {max_id:,}")


print("\n" + "=" * 55)
print("PASO 5 — Eliminando películas duplicadas (ya existentes) ...")
print("=" * 55)

# Obtener títulos+año que ya están en la DB para no duplicar
existing = pd.read_sql(
    f"SELECT title, year FROM movies WHERE year >= {FROM_YEAR}", conn
)
existing['key'] = existing['title'].str.lower() + '_' + existing['year'].astype(str)
merged['key']   = merged['primaryTitle'].str.lower() + '_' + merged['startYear'].astype(str)

before = len(merged)
merged = merged[~merged['key'].isin(existing['key'])]
print(f"✅ Duplicados eliminados: {before - len(merged):,} | Nuevas a insertar: {len(merged):,}")


print("\n" + "=" * 55)
print("PASO 6 — Insertando películas nuevas en movies ...")
print("=" * 55)

# Preparar IDs nuevos
merged = merged.reset_index(drop=True)
merged['new_id'] = merged.index + max_id + 1

movies_to_insert = merged[['new_id', 'primaryTitle', 'startYear']].copy()
movies_to_insert.columns = ['id', 'title', 'year']

movies_to_insert.to_sql('movies', conn, if_exists='append', index=False)
print(f"✅ {len(movies_to_insert):,} películas insertadas en movies")


print("\n" + "=" * 55)
print("PASO 7 — Insertando ratings ...")
print("=" * 55)

ratings_to_insert = merged[['new_id', 'averageRating', 'numVotes']].copy()
ratings_to_insert.columns = ['movie_id', 'rating', 'votes']

ratings_to_insert.to_sql('ratings', conn, if_exists='append', index=False)
print(f"✅ {len(ratings_to_insert):,} ratings insertados")


print("\n" + "=" * 55)
print("PASO 8 — Verificando resultado final ...")
print("=" * 55)

final = cursor.execute("SELECT COUNT(*), MAX(year) FROM movies").fetchone()
print(f"✅ Total final: {final[0]:,} películas | último año: {final[1]}")

conn.commit()
conn.close()

print("\n" + "=" * 55)
print("✅ movies.db actualizado correctamente")
print("=" * 55)

const { Pool } = require('pg');

// Initialize the connection pool using your local.settings.json variables
const pool = new Pool({
    host: process.env.PG_VECTOR_HOST,
    user: process.env.PG_VECTOR_USER,
    password: process.env.PG_VECTOR_PASSWORD,
    port: process.env.PGPORT,
    database: process.env.PGDATABASE6,
    ssl: { 
        rejectUnauthorized: false // Often required for Azure Database for PostgreSQL
    }
});

/**
 * Executes a query against the PostgreSQL database.
 * @param {string} text - The SQL query string.
 * @param {Array} params - Optional parameterized values.
 */
async function query(text, params) {
    const client = await pool.connect();
    try {
        const res = await client.query(text, params);
        return res; // Returning the full result object so res.rowCount, etc. are accessible
    } finally {
        client.release();
    }
}

module.exports = { query };

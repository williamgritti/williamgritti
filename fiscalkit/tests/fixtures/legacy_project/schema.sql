-- Deliberately wrong: a CNPJ cannot be stored as a number from July 2026.
CREATE TABLE fornecedor (
    id SERIAL PRIMARY KEY,
    cnpj BIGINT NOT NULL UNIQUE
);

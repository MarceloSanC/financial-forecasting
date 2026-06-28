"""Pacote shared — preocupações transversais reutilizáveis entre features.

Contém código genuinamente compartilhado: exceções base, value objects genéricos,
ports compartilhados (Clock, IdGenerator) e infraestrutura (config, banco, HTTP).
Regra: shared nunca importa de features/ — o fluxo de dependência é sempre
features → shared, nunca o contrário.
"""

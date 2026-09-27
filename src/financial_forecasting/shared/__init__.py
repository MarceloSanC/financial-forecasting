"""Pacote shared — preocupações transversais reutilizáveis entre features.

Contém código genuinamente compartilhado: exceções base, value objects genéricos,
ports compartilhados (Clock, Hasher, calendário de pregão) e infraestrutura (config, banco, HTTP).
Regra: shared nunca importa de features/ — o fluxo de dependência é sempre
features → shared, nunca o contrário.
"""

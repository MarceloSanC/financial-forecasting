"""Composition Root — único ponto de wiring de dependências da aplicação.

Este módulo é o ÚNICO lugar que conhece as implementações concretas. Ele instancia
cada dependência de infraestrutura e injeta nas camadas de aplicação. Se você
precisar trocar uma implementação (ex: Postgres → DynamoDB), mude APENAS aqui.
Nenhuma regra de negócio deve ser alterada.

Regra: nenhum outro módulo deve instanciar diretamente classes de `infrastructure/`
ou de `adapters/out/`. Sempre receba dependências via construtor (injeção explícita).

Este arquivo nasce vazio no template — adicione campos a `ApplicationDependencies`
e wiring em `wire_dependencies()` conforme as features forem sendo criadas.
"""

from dataclasses import dataclass

from financial_forecasting.shared.infrastructure.config.settings import Settings, get_settings


@dataclass
class ApplicationDependencies:
    """Contêiner com os use cases montados e prontos para uso.

    Exponha aqui apenas o que os adapters primários (ex: routers HTTP) precisam.
    Dependências de infraestrutura (engine, clock) ficam encapsuladas — não vazam.

    Adicione campos conforme as features forem criadas, por exemplo:

        create_payment: CreatePaymentUseCase
    """


def wire_dependencies(settings: Settings | None = None) -> ApplicationDependencies:
    """Monta o grafo de dependências completo e retorna os use cases prontos.

    Chamado uma única vez na inicialização da aplicação (dentro de `create_app()`).
    Em testes, pode ser chamado com um `Settings` fake apontando para um banco
    in-memory ou de teste.

    Template típico de wiring (descomente e adapte conforme as features chegarem):

        from financial_forecasting.features.<feature>.adapters.out.postgres import (
            Postgres<Entity>Repository,
        )
        from financial_forecasting.features.<feature>.application.use_cases import (
            <UseCase>,
        )
        from financial_forecasting.shared.infrastructure.clock.system_clock import (
            SystemClock,
        )
        from financial_forecasting.shared.infrastructure.database.connection import (
            build_engine,
        )
        from financial_forecasting.shared.infrastructure.uuid_generator.uuid4_generator import (
            Uuid4Generator,
        )

        cfg = settings or get_settings()
        engine = build_engine()
        clock = SystemClock()
        id_gen = Uuid4Generator()
        repo = Postgres<Entity>Repository(engine)
        use_case = <UseCase>(repo=repo, id_gen=id_gen, clock=clock)
        return ApplicationDependencies(use_case=use_case)
    """
    # `settings` é resolvido aqui (sem efeito até a primeira feature usar) para
    # validar configuração no boot mesmo num composition root vazio.
    _ = settings or get_settings()
    return ApplicationDependencies()

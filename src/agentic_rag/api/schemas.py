"""Corpos de requisição e resposta da API (ver docs/api.md).

As docstrings das classes e os `description`/`examples` dos campos aparecem no Swagger
(`/api/docs`): escreva-os para quem vai consumir a API.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ErrorOut(BaseModel):
    """Erro da API. A mensagem está em português e pode ser mostrada direto ao usuário."""

    detail: str = Field(description="Mensagem do erro.", examples=["E-mail ou senha incorretos."])


# --- Auth -----------------------------------------------------------------------------


class UserOut(BaseModel):
    """Usuário logado."""

    id: str = Field(
        description="Id do usuário (uuid4). É o `user_id` das memórias e do histórico.",
        examples=["3f2b8c1e-7a4d-4e9b-9c1f-2d6e8a0b4c55"],
    )
    name: str = Field(description="Nome de exibição.", examples=["Marina Souza"])
    email: str = Field(description="E-mail, em minúsculas.", examples=["marina@empresa.com"])
    is_admin: bool = Field(
        description="Administrador: pode gerenciar a base de conhecimento. "
        "O primeiro usuário registrado vira admin.",
        examples=[True],
    )


class RegisterIn(BaseModel):
    """Dados para criar uma conta."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Marina Souza",
                    "email": "marina@empresa.com",
                    "password": "senha-segura-123",
                }
            ]
        }
    )

    name: str = Field(
        min_length=1, max_length=80, description="Nome de exibição (1 a 80 caracteres)."
    )
    email: EmailStr = Field(description="E-mail válido. É normalizado em minúsculas.")
    password: str = Field(min_length=8, max_length=128, description="Senha (8 a 128 caracteres).")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("O nome não pode ficar vazio.")
        return value


class LoginIn(BaseModel):
    """Credenciais de login."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "marina@empresa.com", "password": "senha-segura-123"}]
        }
    )

    email: str = Field(
        min_length=1, max_length=320, description="E-mail da conta (maiúsculas são ignoradas)."
    )
    password: str = Field(min_length=1, max_length=128, description="Senha da conta.")


# --- Status ---------------------------------------------------------------------------


class MetaOut(BaseModel):
    """Configurações públicas que a interface precisa conhecer."""

    llm_model: str = Field(
        description="Modelo de linguagem usado pelo agente.", examples=["gpt-6-luna"]
    )
    langsmith: bool = Field(description="Se o tracing no LangSmith está ligado.", examples=[True])
    upload_max_mb: int = Field(
        description="Tamanho máximo de cada arquivo enviado, em MB.", examples=[20]
    )
    supported_extensions: list[str] = Field(
        description="Extensões aceitas no upload.", examples=[[".md", ".pdf", ".txt"]]
    )


# --- Conversas ------------------------------------------------------------------------


class ConversationSummaryOut(BaseModel):
    """Conversa na listagem do histórico."""

    id: str = Field(
        description="Id da conversa (uuid4). É também o `thread_id` do agente.",
        examples=["9a1c4f2e-5b3d-4c8a-a7e6-1f0d2b3c4e5f"],
    )
    title: str = Field(
        description="Título: a primeira pergunta, truncada em 60 caracteres.",
        examples=["Qual o limite de reembolso para refeição em viagem?"],
    )
    updated_at: datetime = Field(description="Data da última mensagem (ISO 8601, UTC).")


class ToolCallOut(BaseModel):
    """Ferramenta que o agente chamou para responder."""

    name: str = Field(
        description="Nome da ferramenta: `search_policies`, `convert_currency`, "
        "`get_exchange_rate`, `save_memory`, `update_memory` ou `delete_memory`.",
        examples=["convert_currency"],
    )
    args: dict[str, Any] = Field(
        description="Argumentos passados à ferramenta.",
        examples=[{"amount": 30, "currency": "USD"}],
    )


class MessageOut(BaseModel):
    """Mensagem de uma conversa."""

    role: str = Field(description="Autor: `user` ou `assistant`.", examples=["assistant"])
    content: str = Field(
        description="Texto da mensagem (as respostas do assistente vêm em Markdown).",
        examples=["O limite é de **R$ 110,00** por refeição."],
    )
    tools: list[ToolCallOut] = Field(
        description="Ferramentas usadas para gerar a resposta (vazio nas mensagens do usuário)."
    )


class ConversationOut(BaseModel):
    """Conversa completa, com todas as mensagens em ordem."""

    id: str = Field(description="Id da conversa.")
    title: str = Field(description="Título da conversa.")
    messages: list[MessageOut] = Field(description="Mensagens, da mais antiga para a mais nova.")


class ChatIn(BaseModel):
    """Pergunta enviada ao agente."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "conversation_id": None,
                    "message": "Qual o limite de reembolso para refeição em viagem?",
                }
            ]
        }
    )

    conversation_id: str | None = Field(
        default=None,
        description="Id (uuid) de uma conversa do usuário para continuar nela. "
        "`null` começa uma conversa nova; o id criado vem no evento `conversation`.",
    )
    message: str = Field(
        min_length=1, max_length=4000, description="Pergunta (1 a 4000 caracteres)."
    )

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A mensagem não pode ficar vazia.")
        return value

    @field_validator("conversation_id")
    @classmethod
    def _check_id(cls, value: str | None) -> str | None:
        if value is not None:
            uuid.UUID(value)  # ids de conversa são uuid4; ValueError vira 422
        return value


# --- Base de conhecimento -------------------------------------------------------------


class DataFileOut(BaseModel):
    """Arquivo da pasta `data/raw`."""

    name: str = Field(
        description="Nome do arquivo.", examples=["orbita_politica_reembolso_2026.md"]
    )
    size: int = Field(description="Tamanho em bytes.", examples=[5120])


class UploadCheckOut(BaseModel):
    """Resultado da validação de um arquivo (sem gravar nada)."""

    name: str = Field(
        description="Nome final em `data/raw` (sem pastas: `../x.md` vira `x.md`).",
        examples=["politica_viagens.md"],
    )
    size: int = Field(description="Tamanho em bytes.", examples=[2048])
    ok: bool = Field(description="Se o arquivo pode ser enviado.", examples=[True])
    error: str | None = Field(description="Motivo da recusa (`null` se `ok`).", examples=[None])
    injection_signals: list[str] = Field(
        description="Trechos com cara de instrução ao agente. Só alerta: o arquivo ainda "
        "pode ser enviado, e o agente trata o conteúdo como dado.",
        examples=[[]],
    )
    replaces: bool = Field(
        description="Já existe um arquivo com esse nome, que será substituído.", examples=[False]
    )


class IngestionResultOut(BaseModel):
    """Resultado da sincronização da base vetorial com `data/raw`."""

    total: int = Field(description="Chunks na base ao final.", examples=[142])
    added: int = Field(description="Chunks novos ou alterados (geraram embedding).", examples=[12])
    deleted: int = Field(
        description="Chunks removidos (documentos editados ou apagados).", examples=[3]
    )


class UploadErrorOut(BaseModel):
    """Arquivo que não foi salvo."""

    name: str = Field(description="Nome do arquivo.", examples=["planilha.xlsx"])
    message: str = Field(description="Motivo.", examples=["extensão não suportada"])


class UploadResultOut(BaseModel):
    """Resultado do envio de arquivos."""

    saved: list[str] = Field(
        description="Arquivos salvos em `data/raw`.", examples=[["politica_viagens.md"]]
    )
    errors: list[UploadErrorOut] = Field(
        description="Arquivos recusados ou que falharam ao salvar."
    )
    ingestion: IngestionResultOut | None = Field(
        description="Resultado da indexação (`null` se nada foi salvo ou se ela falhou)."
    )
    ingestion_error: str | None = Field(
        description="Mensagem se os arquivos foram salvos mas a indexação falhou."
    )

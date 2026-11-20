# HUAWEI WiFi AX2 — avaliação de cobertura

## Estado: sem integração confirmada

O HUAWEI WiFi AX2 é um roteador doméstico. Para o firmware
`2.0.0.322(SP1C947)`, ainda não foram fornecidos logs exportados nem foi
confirmada na interface uma opção para enviar logs por syslog. As páginas
oficiais de produto descrevem funções de administração e diagnóstico, mas não
documentam exportação contínua de eventos para o Open Security Lakehouse:

- [Especificações AX2](https://consumer.huawei.com/en/routers/ax2/specs/)
- [Recursos AX2](https://consumer.huawei.com/en/routers/ax2/)

Isso **não prova a ausência** de exportação em todas as revisões e regiões.
Documentação de syslog para equipamentos *enterprise* da Huawei não deve ser
usada como prova de suporte no AX2. Até confirmar um método e testar amostras
reais, não cadastrar o roteador como fonte ativa, não criar parser específico
e não interpretar a falta de eventos como falha de um coletor.

## Próximos passos sem alterar o roteador

1. Consultar as opções de diagnóstico/registro na interface web e no AI Life.
   Se houver exportação, identificar formato, período coberto e se é manual ou
   contínua. Confirmar com o suporte da Huawei, informando modelo e firmware,
   se existe saída syslog, API ou exportação de logs nesta revisão.
2. Se houver exportação, obter 5–10 linhas reais (normais e de falha) e
   sanitizar antes de compartilhar: substituir IP público, MAC, número de
   série, SSID, usuário, tokens e outros identificadores. Guardar o arquivo
   original fora do repositório, em local protegido.
3. Só após verificar o formato, implementar um adaptador dedicado com testes
   de parsing, rejeição de entradas inválidas e preservação do original.
   Identificar explicitamente a origem e não atribuir conformidade OCSF
   somente por nomear o esquema.
4. Se não houver saída, manter o AX2 como lacuna de cobertura **documentada**.
   Coletar eventos nos endpoints Linux/Windows e nos serviços críticos, usando
   as fontes que a plataforma já suporta. Isso não substitui logs do firewall,
   conexões recusadas no roteador nem histórico de associações Wi-Fi.
5. Se a visibilidade de borda for necessária, avaliar um firewall/gateway
   separado que publique logs, sujeito a planejamento de rede, custo e
   disponibilidade. Não presumir que monitorar um host na LAN permite enxergar
   todo o tráfego WAN/Wi-Fi; inspeção de tráfego exigiria um ponto de observação
   apropriado e tratamento de privacidade.

Não habilitar um listener UDP/syslog sem autenticação na rede nem fazer scraping
de interfaces internas ou usar credenciais administrativas do roteador no lake
apenas para contornar a ausência de exportação documentada. O coletor de rede
atual recebe syslog **TCP com mTLS**: uma saída syslog UDP simples do aparelho,
se descoberta, não seria diretamente compatível.

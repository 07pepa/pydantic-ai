import json
from dataclasses import replace

import pytest
from inline_snapshot import snapshot
from pydantic import BaseModel
from typing_extensions import TypedDict

from pydantic_ai.agent import Agent
from pydantic_ai.exceptions import ModelHTTPError, ModelRetry
from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.output import NativeOutput, PromptedOutput, TextOutput, ToolOutput
from pydantic_ai.profiles.openai import openai_model_profile
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import Usage

from ..conftest import IsDatetime, IsStr, TestEnv, try_import

with try_import() as imports_successful:
    from pydantic_ai.models.openai import OpenAIModelSettings, OpenAIResponsesModel, OpenAIResponsesModelSettings
    from pydantic_ai.providers.openai import OpenAIProvider

pytestmark = [
    pytest.mark.skipif(not imports_successful(), reason='openai not installed'),
    pytest.mark.anyio,
    pytest.mark.vcr,
]


def test_openai_responses_model(env: TestEnv):
    env.set('OPENAI_API_KEY', 'test')
    model = OpenAIResponsesModel('gpt-4o')
    assert model.model_name == 'gpt-4o'
    assert model.system == 'openai'


async def test_openai_responses_model_simple_response(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(model=model)
    result = await agent.run('What is the capital of France?')
    assert result.output == snapshot('The capital of France is Paris.')


async def test_openai_responses_model_simple_response_with_tool_call(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))

    agent = Agent(model=model)

    @agent.tool_plain
    async def get_capital(country: str) -> str:
        return 'Potato City'

    result = await agent.run('What is the capital of PotatoLand?')
    assert result.output == snapshot('The capital of PotatoLand is Potato City.')


async def test_openai_responses_output_type(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))

    class MyOutput(TypedDict):
        name: str
        age: int

    agent = Agent(model=model, output_type=MyOutput)
    result = await agent.run('Give me the name and age of Brazil, Argentina, and Chile.')
    assert result.output == snapshot({'name': 'Brazil', 'age': 2023})


async def test_openai_responses_reasoning_effort(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('o3-mini', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(model=model, model_settings=OpenAIModelSettings(openai_reasoning_effort='low'))
    result = await agent.run(
        'Explain me how to cook uruguayan alfajor. Do not send whitespaces at the end of the lines.'
    )
    assert [line.strip() for line in result.output.splitlines()] == snapshot(
        [
            'Ingredients for the dough:',
            '• 300 g cornstarch',
            '• 200 g flour',
            '• 150 g powdered sugar',
            '• 200 g unsalted butter',
            '• 3 egg yolks',
            '• Zest of 1 lemon',
            '• 1 teaspoon vanilla extract',
            '• A pinch of salt',
            '',
            'Ingredients for the filling (dulce de leche):',
            '• 400 g dulce de leche',
            '',
            'Optional coating:',
            '• Powdered sugar for dusting',
            '• Grated coconut',
            '• Crushed peanuts or walnuts',
            '• Melted chocolate',
            '',
            'Steps:',
            '1. In a bowl, mix together the cornstarch, flour, powdered sugar, and salt.',
            '2. Add the unsalted butter cut into small pieces. Work it into the dry ingredients until the mixture resembles coarse breadcrumbs.',
            '3. Incorporate the egg yolks, lemon zest, and vanilla extract. Mix until you obtain a smooth and homogeneous dough.',
            '4. Wrap the dough in plastic wrap and let it rest in the refrigerator for at least one hour.',
            '5. Meanwhile, prepare a clean workspace by lightly dusting it with flour.',
            '6. Roll out the dough on the working surface until it is about 0.5 cm thick.',
            '7. Use a round cutter (approximately 3-4 cm in diameter) to cut out circles. Re-roll any scraps to maximize the number of cookies.',
            '8. Arrange the circles on a baking sheet lined with parchment paper.',
            '9. Preheat the oven to 180°C (350°F) and bake the cookies for about 10-12 minutes until they are lightly golden at the edges. They should remain soft.',
            '10. Remove the cookies from the oven and allow them to cool completely on a rack.',
            '11. Once the cookies are cool, spread dulce de leche on the flat side of one cookie and sandwich it with another.',
            '12. If desired, roll the edges of the alfajores in powdered sugar, grated coconut, crushed nuts, or dip them in melted chocolate.',
            '13. Allow any coatings to set before serving.',
            '',
            'Enjoy your homemade Uruguayan alfajores!',
        ]
    )


async def test_openai_responses_reasoning_generate_summary(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('computer-use-preview', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(
        model=model,
        model_settings=OpenAIResponsesModelSettings(
            openai_reasoning_summary='concise',
            openai_truncation='auto',
        ),
    )
    result = await agent.run('What should I do to cross the street?')
    assert result.output == snapshot("""\
To cross the street safely, follow these steps:

1. **Use a Crosswalk**: Always use a designated crosswalk or pedestrian crossing whenever available.
2. **Press the Button**: If there is a pedestrian signal button, press it and wait for the signal.
3. **Look Both Ways**: Look left, right, and left again before stepping off the curb.
4. **Wait for the Signal**: Cross only when the pedestrian signal indicates it is safe to do so or when there is a clear gap in traffic.
5. **Stay Alert**: Be mindful of turning vehicles and stay attentive while crossing.
6. **Walk, Don't Run**: Walk across the street; running can increase the risk of falling or not noticing an oncoming vehicle.

Always follow local traffic rules and be cautious, even when crossing at a crosswalk. Safety is the priority.\
""")


async def test_openai_responses_system_prompt(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(model=model, system_prompt='You are a helpful assistant.')
    result = await agent.run('What is the capital of France?')
    assert result.output == snapshot('The capital of France is Paris.')


async def test_openai_responses_model_retry(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(model=model)

    @agent.tool_plain
    async def get_location(loc_name: str) -> str:
        if loc_name == 'London':
            return json.dumps({'lat': 51, 'lng': 0})
        else:
            raise ModelRetry('Wrong location, I only know about "London".')

    result = await agent.run('What is the location of Londos and London?')
    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content='What is the location of Londos and London?',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name='get_location',
                        args='{"loc_name":"Londos"}',
                        tool_call_id=IsStr(),
                    ),
                    ToolCallPart(
                        tool_name='get_location',
                        args='{"loc_name":"London"}',
                        tool_call_id=IsStr(),
                    ),
                ],
                usage=Usage(
                    request_tokens=0,
                    response_tokens=0,
                    total_tokens=0,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_67e547c48c9481918c5c4394464ce0c60ae6111e84dd5c08',
            ),
            ModelRequest(
                parts=[
                    RetryPromptPart(
                        content='Wrong location, I only know about "London".',
                        tool_name='get_location',
                        tool_call_id=IsStr(),
                        timestamp=IsDatetime(),
                    ),
                    ToolReturnPart(
                        tool_name='get_location',
                        content='{"lat": 51, "lng": 0}',
                        tool_call_id=IsStr(),
                        timestamp=IsDatetime(),
                    ),
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content="""\
It seems "Londos" might be incorrect or unknown. If you meant something else, please clarify.

For **London**, it's located at approximately latitude 51° N and longitude 0° W.\
"""
                    )
                ],
                usage=Usage(
                    request_tokens=335,
                    response_tokens=44,
                    total_tokens=379,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_67e547c5a2f08191802a1f43620f348503a2086afed73b47',
            ),
        ]
    )


@pytest.mark.vcr()
async def test_image_as_binary_content_tool_response(
    allow_model_requests: None, image_content: BinaryContent, openai_api_key: str
):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m)

    @agent.tool_plain
    async def get_image() -> BinaryContent:
        return image_content

    result = await agent.run(['What fruit is in the image you can get from the get_image tool?'])
    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=['What fruit is in the image you can get from the get_image tool?'],
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[ToolCallPart(tool_name='get_image', args='{}', tool_call_id=IsStr())],
                usage=Usage(
                    request_tokens=40,
                    response_tokens=11,
                    total_tokens=51,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_681134d3aa3481919ca581a267db1e510fe7a5a4e2123dc3',
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='get_image',
                        content='See file 1c8566',
                        tool_call_id='call_FLm3B1f8QAan0KpbUXhNY8bA',
                        timestamp=IsDatetime(),
                    ),
                    UserPromptPart(
                        content=[
                            'This is file 1c8566:',
                            image_content,
                        ],
                        timestamp=IsDatetime(),
                    ),
                ]
            ),
            ModelResponse(
                parts=[TextPart(content='The fruit in the image is a kiwi.')],
                usage=Usage(
                    request_tokens=1185,
                    response_tokens=11,
                    total_tokens=1196,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_681134d53c48819198ce7b89db78dffd02cbfeaababb040c',
            ),
        ]
    )


async def test_image_as_binary_content_input(
    allow_model_requests: None, image_content: BinaryContent, openai_api_key: str
):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m)

    result = await agent.run(['What fruit is in the image?', image_content])
    assert result.output == snapshot('The fruit in the image is a kiwi.')


async def test_openai_responses_audio_as_binary_content_input(
    allow_model_requests: None, audio_content: BinaryContent, openai_api_key: str
):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m)

    with pytest.raises(NotImplementedError):
        await agent.run(['Whose name is mentioned in the audio?', audio_content])


async def test_openai_responses_document_as_binary_content_input(
    allow_model_requests: None, document_content: BinaryContent, openai_api_key: str
):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m)

    result = await agent.run(['What is in the document?', document_content])
    assert result.output == snapshot('The document contains the text "Dummy PDF file."')


async def test_openai_responses_document_url_input(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m)

    document_url = DocumentUrl(url='https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf')

    result = await agent.run(['What is the main content on this document?', document_url])
    assert result.output == snapshot(
        'The main content of this document is a simple text placeholder: "Dummy PDF file."'
    )


async def test_openai_responses_text_document_url_input(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m)

    text_document_url = DocumentUrl(url='https://example-files.online-convert.com/document/txt/example.txt')

    result = await agent.run(['What is the main content on this document?', text_document_url])
    assert result.output == snapshot(
        'The main content of this document is an example of a TXT file type, with an explanation of the use of placeholder names like "John Doe" and "Jane Doe" in legal, medical, and other contexts. It discusses the practice in the U.S. and Canada, mentions equivalent practices in other English-speaking countries, and touches on cultural references. The document also notes that it\'s an example file created by an online conversion tool, with content sourced from Wikipedia under a Creative Commons license.'
    )


async def test_openai_responses_image_url_input(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m)

    result = await agent.run(
        [
            'hello',
            ImageUrl(url='https://t3.ftcdn.net/jpg/00/85/79/92/360_F_85799278_0BBGV9OAdQDTLnKwAPBCcg1J7QtiieJY.jpg'),
        ]
    )
    assert result.output == snapshot("Hello! I see you've shared an image of a potato. How can I assist you today?")


async def test_openai_responses_stream(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(model=model)

    @agent.tool_plain
    async def get_capital(country: str) -> str:
        return 'Paris'

    output_text: list[str] = []
    async with agent.run_stream('What is the capital of France?') as result:
        async for output in result.stream_text():
            output_text.append(output)

    assert output_text == snapshot(['The capital of France is Paris.'])


async def test_openai_responses_model_http_error(allow_model_requests: None, openai_api_key: str):
    """Set temperature to -1 to trigger an error, given only values between 0 and 1 are allowed."""
    model = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(model=model, model_settings=OpenAIModelSettings(temperature=-1))

    with pytest.raises(ModelHTTPError):
        async with agent.run_stream('What is the capital of France?'):
            ...  # pragma: lax no cover


async def test_openai_responses_model_builtin_tools(allow_model_requests: None, openai_api_key: str):
    model = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    settings = OpenAIResponsesModelSettings(openai_builtin_tools=[{'type': 'web_search_preview'}])
    agent = Agent(model=model, model_settings=settings)
    result = await agent.run('Give me the best news about LLMs from the last 24 hours. Be short.')

    # NOTE: We don't have the tool call because OpenAI calls the tool internally.
    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content='Give me the best news about LLMs from the last 24 hours. Be short.',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content="""\
In the past 24 hours, OpenAI announced plans to release its first open-weight language model with reasoning capabilities since GPT-2. This model will allow developers to fine-tune it for specific applications without needing the original training data. To gather feedback and refine the model, OpenAI will host developer events starting in San Francisco and expanding to Europe and Asia-Pacific regions. ([reuters.com](https://www.reuters.com/technology/artificial-intelligence/openai-plans-release-open-weight-language-model-coming-months-2025-03-31/?utm_source=openai))


## OpenAI to Release Open-Weight Language Model:
- [OpenAI plans to release open-weight language model in coming months](https://www.reuters.com/technology/artificial-intelligence/openai-plans-release-open-weight-language-model-coming-months-2025-03-31/?utm_source=openai) \
"""
                    )
                ],
                usage=Usage(
                    request_tokens=320,
                    response_tokens=200,
                    total_tokens=520,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_67ebcbb93728819197f923ff16e98bce04f5055a2a33abc3',
            ),
        ]
    )


@pytest.mark.vcr()
async def test_openai_responses_model_instructions(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m, instructions='You are a helpful assistant.')

    result = await agent.run('What is the capital of France?')
    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[UserPromptPart(content='What is the capital of France?', timestamp=IsDatetime())],
                instructions='You are a helpful assistant.',
            ),
            ModelResponse(
                parts=[TextPart(content='The capital of France is Paris.')],
                usage=Usage(
                    request_tokens=24,
                    response_tokens=8,
                    total_tokens=32,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_67f3fdfd9fa08191a3d5825db81b8df6003bc73febb56d77',
            ),
        ]
    )


def test_model_profile_strict_not_supported():
    my_tool = ToolDefinition(
        name='my_tool',
        description='This is my tool',
        parameters_json_schema={'type': 'object', 'title': 'Result', 'properties': {'spam': {'type': 'number'}}},
        strict=True,
    )

    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key='foobar'))
    tool_param = m._map_tool_definition(my_tool)  # type: ignore[reportPrivateUsage]

    assert tool_param == snapshot(
        {
            'name': 'my_tool',
            'parameters': {'type': 'object', 'title': 'Result', 'properties': {'spam': {'type': 'number'}}},
            'type': 'function',
            'description': 'This is my tool',
            'strict': True,
        }
    )

    # Some models don't support strict tool definitions
    m = OpenAIResponsesModel(
        'gpt-4o',
        provider=OpenAIProvider(api_key='foobar'),
        profile=replace(openai_model_profile('gpt-4o'), openai_supports_strict_tool_definition=False),
    )
    tool_param = m._map_tool_definition(my_tool)  # type: ignore[reportPrivateUsage]

    assert tool_param == snapshot(
        {
            'name': 'my_tool',
            'parameters': {'type': 'object', 'title': 'Result', 'properties': {'spam': {'type': 'number'}}},
            'type': 'function',
            'description': 'This is my tool',
            'strict': False,
        }
    )


@pytest.mark.vcr()
async def test_reasoning_model_with_temperature(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('o3-mini', provider=OpenAIProvider(api_key=openai_api_key))
    agent = Agent(m, model_settings=OpenAIResponsesModelSettings(temperature=0.5))
    result = await agent.run('What is the capital of Mexico?')
    assert result.output == snapshot(
        'The capital of Mexico is Mexico City. It serves as the political, cultural, and economic heart of the country and is one of the largest metropolitan areas in the world.'
    )


@pytest.mark.vcr()
async def test_tool_output(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))

    class CityLocation(BaseModel):
        city: str
        country: str

    agent = Agent(m, output_type=ToolOutput(CityLocation))

    @agent.tool_plain
    async def get_user_country() -> str:
        return 'Mexico'

    result = await agent.run('What is the largest city in the user country?')
    assert result.output == snapshot(CityLocation(city='Mexico City', country='Mexico'))

    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content='What is the largest city in the user country?',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[ToolCallPart(tool_name='get_user_country', args='{}', tool_call_id=IsStr())],
                usage=Usage(
                    request_tokens=62,
                    response_tokens=12,
                    total_tokens=74,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68477f0b40a8819cb8d55594bc2c232a001fd29e2d5573f7',
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='get_user_country',
                        content='Mexico',
                        tool_call_id='call_ZWkVhdUjupo528U9dqgFeRkH',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name='final_result',
                        args='{"city":"Mexico City","country":"Mexico"}',
                        tool_call_id='call_iFBd0zULhSZRR908DfH73VwN',
                    )
                ],
                usage=Usage(
                    request_tokens=85,
                    response_tokens=20,
                    total_tokens=105,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68477f0bfda8819ea65458cd7cc389b801dc81d4bc91f560',
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='final_result',
                        content='Final result processed.',
                        tool_call_id='call_iFBd0zULhSZRR908DfH73VwN',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
        ]
    )


@pytest.mark.vcr()
async def test_text_output_function(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))

    def upcase(text: str) -> str:
        return text.upper()

    agent = Agent(m, output_type=TextOutput(upcase))

    @agent.tool_plain
    async def get_user_country() -> str:
        return 'Mexico'

    result = await agent.run('What is the largest city in the user country?')
    assert result.output == snapshot('THE LARGEST CITY IN MEXICO IS MEXICO CITY.')

    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content='What is the largest city in the user country?',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[
                    ToolCallPart(tool_name='get_user_country', args='{}', tool_call_id='call_aTJhYjzmixZaVGqwl5gn2Ncr')
                ],
                usage=Usage(
                    request_tokens=36,
                    response_tokens=12,
                    total_tokens=48,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68477f0d9494819ea4f123bba707c9ee0356a60c98816d6a',
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='get_user_country',
                        content='Mexico',
                        tool_call_id='call_aTJhYjzmixZaVGqwl5gn2Ncr',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[TextPart(content='The largest city in Mexico is Mexico City.')],
                usage=Usage(
                    request_tokens=59,
                    response_tokens=11,
                    total_tokens=70,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68477f0e2b28819d9c828ef4ee526d6a03434b607c02582d',
            ),
        ]
    )


@pytest.mark.vcr()
async def test_native_output(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))

    class CityLocation(BaseModel):
        """A city and its country."""

        city: str
        country: str

    agent = Agent(m, output_type=NativeOutput(CityLocation))

    @agent.tool_plain
    async def get_user_country() -> str:
        return 'Mexico'

    result = await agent.run('What is the largest city in the user country?')
    assert result.output == snapshot(CityLocation(city='Mexico City', country='Mexico'))

    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content='What is the largest city in the user country?',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[ToolCallPart(tool_name='get_user_country', args='{}', tool_call_id=IsStr())],
                usage=Usage(
                    request_tokens=66,
                    response_tokens=12,
                    total_tokens=78,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68477f0f220081a1a621d6bcdc7f31a50b8591d9001d2329',
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='get_user_country',
                        content='Mexico',
                        tool_call_id='call_tTAThu8l2S9hNky2krdwijGP',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[TextPart(content='{"city":"Mexico City","country":"Mexico"}')],
                usage=Usage(
                    request_tokens=89,
                    response_tokens=16,
                    total_tokens=105,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68477f0fde708192989000a62809c6e5020197534e39cc1f',
            ),
        ]
    )


@pytest.mark.vcr()
async def test_native_output_multiple(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))

    class CityLocation(BaseModel):
        city: str
        country: str

    class CountryLanguage(BaseModel):
        country: str
        language: str

    agent = Agent(m, output_type=NativeOutput([CityLocation, CountryLanguage]))

    @agent.tool_plain
    async def get_user_country() -> str:
        return 'Mexico'

    result = await agent.run('What is the largest city in the user country?')
    assert result.output == snapshot(CityLocation(city='Mexico City', country='Mexico'))

    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content='What is the largest city in the user country?',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[ToolCallPart(tool_name='get_user_country', args='{}', tool_call_id=IsStr())],
                usage=Usage(
                    request_tokens=153,
                    response_tokens=12,
                    total_tokens=165,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68477f10f2d081a39b3438f413b3bafc0dd57d732903c563',
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='get_user_country',
                        content='Mexico',
                        tool_call_id='call_UaLahjOtaM2tTyYZLxTCbOaP',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content='{"result":{"kind":"CityLocation","data":{"city":"Mexico City","country":"Mexico"}}}'
                    )
                ],
                usage=Usage(
                    request_tokens=176,
                    response_tokens=26,
                    total_tokens=202,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68477f119830819da162aa6e10552035061ad97e2eef7871',
            ),
        ]
    )


@pytest.mark.vcr()
async def test_prompted_output(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))

    class CityLocation(BaseModel):
        city: str
        country: str

    agent = Agent(m, output_type=PromptedOutput(CityLocation))

    @agent.tool_plain
    async def get_user_country() -> str:
        return 'Mexico'

    result = await agent.run('What is the largest city in the user country?')
    assert result.output == snapshot(CityLocation(city='Mexico City', country='Mexico'))

    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content='What is the largest city in the user country?',
                        timestamp=IsDatetime(),
                    )
                ],
                instructions="""\
Always respond with a JSON object that's compatible with this schema:

{"properties": {"city": {"type": "string"}, "country": {"type": "string"}}, "required": ["city", "country"], "title": "CityLocation", "type": "object"}

Don't include any text or Markdown fencing before or after.\
""",
            ),
            ModelResponse(
                parts=[ToolCallPart(tool_name='get_user_country', args='{}', tool_call_id=IsStr())],
                usage=Usage(
                    request_tokens=107,
                    response_tokens=12,
                    total_tokens=119,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68482f12d63881a1830201ed101ecfbf02f8ef7f2fb42b50',
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='get_user_country',
                        content='Mexico',
                        tool_call_id='call_FrlL4M0CbAy8Dhv4VqF1Shom',
                        timestamp=IsDatetime(),
                    )
                ],
                instructions="""\
Always respond with a JSON object that's compatible with this schema:

{"properties": {"city": {"type": "string"}, "country": {"type": "string"}}, "required": ["city", "country"], "title": "CityLocation", "type": "object"}

Don't include any text or Markdown fencing before or after.\
""",
            ),
            ModelResponse(
                parts=[TextPart(content='{"city":"Mexico City","country":"Mexico"}')],
                usage=Usage(
                    request_tokens=130,
                    response_tokens=12,
                    total_tokens=142,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68482f1b556081918d64c9088a470bf0044fdb7d019d4115',
            ),
        ]
    )


@pytest.mark.vcr()
async def test_prompted_output_multiple(allow_model_requests: None, openai_api_key: str):
    m = OpenAIResponsesModel('gpt-4o', provider=OpenAIProvider(api_key=openai_api_key))

    class CityLocation(BaseModel):
        city: str
        country: str

    class CountryLanguage(BaseModel):
        country: str
        language: str

    agent = Agent(m, output_type=PromptedOutput([CityLocation, CountryLanguage]))

    @agent.tool_plain
    async def get_user_country() -> str:
        return 'Mexico'

    result = await agent.run('What is the largest city in the user country?')
    assert result.output == snapshot(CityLocation(city='Mexico City', country='Mexico'))

    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content='What is the largest city in the user country?',
                        timestamp=IsDatetime(),
                    )
                ],
                instructions="""\
Always respond with a JSON object that's compatible with this schema:

{"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "CityLocation"}, "data": {"properties": {"city": {"type": "string"}, "country": {"type": "string"}}, "required": ["city", "country"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "CityLocation"}, {"type": "object", "properties": {"kind": {"type": "string", "const": "CountryLanguage"}, "data": {"properties": {"country": {"type": "string"}, "language": {"type": "string"}}, "required": ["country", "language"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "CountryLanguage"}]}}, "required": ["result"], "additionalProperties": false}

Don't include any text or Markdown fencing before or after.\
""",
            ),
            ModelResponse(
                parts=[ToolCallPart(tool_name='get_user_country', args='{}', tool_call_id=IsStr())],
                usage=Usage(
                    request_tokens=283,
                    response_tokens=12,
                    total_tokens=295,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68482f1d38e081a1ac828acda978aa6b08e79646fe74d5ee',
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='get_user_country',
                        content='Mexico',
                        tool_call_id='call_my4OyoVXRT0m7bLWmsxcaCQI',
                        timestamp=IsDatetime(),
                    )
                ],
                instructions="""\
Always respond with a JSON object that's compatible with this schema:

{"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "CityLocation"}, "data": {"properties": {"city": {"type": "string"}, "country": {"type": "string"}}, "required": ["city", "country"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "CityLocation"}, {"type": "object", "properties": {"kind": {"type": "string", "const": "CountryLanguage"}, "data": {"properties": {"country": {"type": "string"}, "language": {"type": "string"}}, "required": ["country", "language"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "CountryLanguage"}]}}, "required": ["result"], "additionalProperties": false}

Don't include any text or Markdown fencing before or after.\
""",
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content='{"result":{"kind":"CityLocation","data":{"city":"Mexico City","country":"Mexico"}}}'
                    )
                ],
                usage=Usage(
                    request_tokens=306,
                    response_tokens=22,
                    total_tokens=328,
                    details={'reasoning_tokens': 0, 'cached_tokens': 0},
                ),
                model_name='gpt-4o-2024-08-06',
                timestamp=IsDatetime(),
                vendor_id='resp_68482f28c1b081a1ae73cbbee012ee4906b4ab2d00d03024',
            ),
        ]
    )

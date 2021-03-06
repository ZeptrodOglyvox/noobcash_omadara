import json
import backend as node
from backend.blockchain import Blockchain


def assert_json_200(response):
    """
    check if response gucci
    """
    assert response.content_type == 'application/json'
    assert response.status_code == 200


def test_mine_block(test_client, node_setup, test_block, test_transaction):
    result = node.blkchain.add_block(test_block)
    assert not isinstance(result, str)
    assert test_block == node.blkchain.last_block
    assert test_transaction in test_block.transactions
    assert test_transaction in node.blkchain.last_block.transactions


def test_get_chain(test_client, node_setup, test_block):
    response = test_client.get('blockchain/get_chain')
    assert_json_200(response)
    data = response.get_json()
    bc = Blockchain.from_dict(data)

    assert len(node.blkchain) == data['length']
    assert bc == node.blkchain



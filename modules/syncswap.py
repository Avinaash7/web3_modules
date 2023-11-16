

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import random
from web3 import Web3
from time import sleep
import json
from eth_abi import abi
from utils.wallet_tools import WalletTool
from utils.utilities import Receipt, determine_decimals, get_amount, check_and_compare_balance, get_swap_deadline
import time
from loguru import logger as LOGGER

with open('coinData.json', 'r') as f:
    coin_data = json.load(f)

# pip freeze, pip install eth_abi


from config import (
    SYNCSWAP_CLASSIC_POOL_ABI,
    ZERO_ADDRESS,
    SYNCSWAP_CONTRACTS,
    SYNCSWAP_ROUTER_ABI,
    SYNCSWAP_CLASSIC_POOL_DATA_ABI,
    ZKSYNC_TOKENS

)

class SyncSwap(WalletTool):
    def __init__(self, acc: WalletTool) -> None:
        super().__init__(acc)
        self.id = 'id placeholder' #ignore this
        wallet = WalletTool(acc)
        self.swap_contract = self.get_contract(SYNCSWAP_CONTRACTS["router"], SYNCSWAP_ROUTER_ABI)
        self.nonce = self.get_nonce('ZK')
        self.tx = {
            "from": wallet.checksum_address,
            "gasPrice": self.w3.eth.gas_price,
            "nonce": self.nonce
        }

    def get_pool(self, sell_token: str, buy_token: str):
        contract = self.get_contract(SYNCSWAP_CONTRACTS["classic_pool"], SYNCSWAP_CLASSIC_POOL_ABI)

        pool_address = contract.functions.getPool(
            Web3.to_checksum_address(ZKSYNC_TOKENS[sell_token]),
            Web3.to_checksum_address(ZKSYNC_TOKENS[buy_token])
        ).call()

        return pool_address

    #TODO randomize slippage
    #TODO move some of these functions to a swap utility class
    def get_min_amount_out(self, pool_address: str, token_address: str, amount: int, slippage: float):
        pool_contract = self.get_contract(pool_address, SYNCSWAP_CLASSIC_POOL_DATA_ABI)
        min_amount_out = pool_contract.functions.getAmountOut(
            token_address,
            amount,
            self.checksum_address,
        ).call()
        return int(min_amount_out - (min_amount_out * (1-slippage)))

    def swap(
            self,
            sell_token: str,
            buy_token: str,
            slippage: float,
            amount
    ):
        token_address = Web3.to_checksum_address(ZKSYNC_TOKENS[sell_token])

        buy_token_decimals, sell_token_decimals = determine_decimals(buy_token, sell_token, coin_data)

        amount_parsed = get_amount(
            sell_token,
            amount,
            sell_token_decimals,
        )

        LOGGER.info(
            f"[{self.id}][{self.pubkey}] Swap on SyncSwap – {sell_token} -> {buy_token} |Sell {amount} {sell_token}"
        )

        pool_address = self.get_pool(sell_token, buy_token)

        if pool_address != ZERO_ADDRESS:
            if sell_token == "ETH":
                self.tx.update({"value": amount_parsed})
            else:
                if self.approve(amount_parsed, token_address, Web3.to_checksum_address(SYNCSWAP_CONTRACTS["router"])):
                    self.tx.update({"nonce": self.get_nonce('ZK')})

            min_amount_out = self.get_min_amount_out(pool_address, token_address, amount_parsed, slippage)

            steps = [{
                "pool": pool_address,
                "data": abi.encode(["address", "address", "uint8"], [token_address, self.pubkey, 1]),
                "callback": ZERO_ADDRESS,
                "callbackData": "0x"
            }]

            paths = [{
                "steps": steps,
                "tokenIn": ZERO_ADDRESS if sell_token == "ETH" else token_address,
                "amountIn": amount_parsed
            }]

            deadline_options = [300, 600, 900, 1200]
            deadline = get_swap_deadline()

            tx = self.tx

            # try:
            LOGGER.info(f'[PK: {self.id}] Sending Syncswap transaction...')
            contract_txn = self.swap_contract.functions.swap(
                paths,
                min_amount_out,
                deadline
            ).build_transaction(self.tx)

            signed_txn = self.sign(contract_txn)

            txn_hash = self.send_raw_transaction(signed_txn)

            receipt = self.wait_until_tx_finished(txn_hash.hex())

            return txn_hash.hex(), receipt
            # except Exception as e:
                # LOGGER.error(f"[PK: {self.id}][{self.pubkey}] SyncSwap failed: {e}")
                # return False

        else:
            LOGGER.error(f"[PK: {self.id}][{self.pubkey}] Swap path {sell_token} to {buy_token} not found!")

if __name__ == '__main__':
    with open('privkey.txt','r') as f:
        privkey = f.read()
    syncswap_instance = SyncSwap(privkey)
    #syncswap_instance.swap('ETH','USDC',.02,0.01)
    syncswap_instance.swap('ETH','USDC',.01,0.001)

    #pool = syncswap_instance.get_pool('ETH', 'USDC')

    #syncswap_instance.get_min_amount_out(pool, )

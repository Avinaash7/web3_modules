import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import random
from web3 import Web3
from time import sleep
import json
from eth_abi import abi
from utils.wallet_tools import WalletTool
from utils.utilities import Receipt, determine_decimals, get_amount
import time
from loguru import logger as LOGGER

with open('coinData.json', 'r') as f:
    coin_data = json.load(f)

from config import (
    ZERO_ADDRESS,
    MAVERICK_CONTRACTS,
    MAVERICK_ROUTER_ABI,
    ZKSYNC_TOKENS,
    MAVERICK_POOLS,
    MAVERICK_POSITION_ABI

)

class Maverick(WalletTool):
    def __init__(self, acc: WalletTool) -> None:
        super().__init__(acc)
        self.id = 'id placeholder' #ignore this
        wallet = WalletTool(acc)
        self.swap_contract = self.get_contract(MAVERICK_CONTRACTS["router"], MAVERICK_ROUTER_ABI)
        self.nonce = self.get_nonce('ZK')
        self.tx = {
            "from": wallet.checksum_address,
            "gasPrice": self.w3.eth.gas_price,
            "nonce": self.nonce
        }
    
    async def get_min_amount_out(self, amount: int, token_a_in: bool, slippage: float):
        contract = self.get_contract(MAVERICK_CONTRACTS["pool_information"], MAVERICK_POSITION_ABI)

        amount = await contract.functions.calculateSwap(
            Web3.to_checksum_address(MAVERICK_CONTRACTS["pool"]),
            amount,
            token_a_in,
            True,
            0
        ).call()

        return int(amount - (amount / 100 * slippage))

    def get_pool(self, sell_token: str, buy_token: str):
          if sell_token+'/'+buy_token  in MAVERICK_POOLS:
            pool_address = MAVERICK_POOLS.get(sell_token+'/'+buy_token)
        
          elif buy_token+'/'+sell_token in MAVERICK_POOLS:
            pool_address = MAVERICK_POOLS.get(buy_token+'/'+sell_token)
          else:
            pool_address = ZERO_ADDRESS
        
          return pool_address
    
    async def get_path(self, from_token: str, to_token: str):
        path_data = [
            Web3.to_checksum_address(ZKSYNC_TOKENS[from_token]),
            Web3.to_checksum_address(MAVERICK_CONTRACTS["pool"]),
            Web3.to_checksum_address(ZKSYNC_TOKENS[to_token]),
        ]

        path = b"".join([bytes.fromhex(address[2:]) for address in path_data])

        return path
    
    async def get_path_token(self, from_token: str, to_token: str, pool_address: str):
        path_data = [
            Web3.to_checksum_address(ZKSYNC_TOKENS[from_token]),
            Web3.to_checksum_address(pool_address),
            Web3.to_checksum_address(ZKSYNC_TOKENS[to_token]),
        ]

        path = b"".join([bytes.fromhex(address[2:]) for address in path_data])
        return path
    
    async def swap_to_token(self, from_token: str, to_token: str, amount: int, slippage: int):
        tx_data = await self.get_tx_data(amount)

        deadline = int(time.time()) + 1000000

        min_amount_out = await self.get_min_amount_out(amount, True, slippage)

        transaction_data = self.swap_contract.encodeABI(
            fn_name="exactInput",
            args=[(
                self.get_path(from_token, to_token),
                self.address,
                deadline,
                amount,
                min_amount_out
            )]
        )

        refund_data = self.swap_contract.encodeABI(
            fn_name="refundETH",
        )

        contract_txn = await self.swap_contract.functions.multicall(
            [transaction_data, refund_data]
        ).build_transaction(tx_data)
        print("Contract TXN:-",contract_txn)
        return contract_txn
    
    async def swap_tokenA_to_tokenB(self, from_token: str, to_token: str, amount: int, slippage: int, pool_address: str):
        await self.approve(amount, ZKSYNC_TOKENS[from_token], MAVERICK_CONTRACTS["router"])
        tx_data = await self.get_tx_data()
        deadline = int(time.time()) + 1000000
        # min_amount_out = await self.get_min_amount_out_token(amount, True, slippage, pool_address)
        min_amount_out = 0
        exact_input_params = {
            "path": self.get_path_token(from_token, to_token, pool_address),
            "recipient": self.address,
            "deadline": deadline,
            "amountIn": amount,
            "amountOutMinimum": min_amount_out
        }
        contract_txn = await self.swap_contract.functions.exactInput(
            exact_input_params
        ).build_transaction(tx_data)
        return contract_txn
    
    async def swap_to_eth(self, from_token: str, to_token: str, amount: int, slippage: int):
        await self.approve(amount, ZKSYNC_TOKENS[from_token], Web3.to_checksum_address(MAVERICK_CONTRACTS["router"]))

        tx_data = await self.get_tx_data()

        deadline = int(time.time()) + 1000000

        min_amount_out = await self.get_min_amount_out(amount, False, slippage)

        transaction_data = self.swap_contract.encodeABI(
            fn_name="exactInput",
            args=[(
                self.get_path(from_token, to_token),
                ZERO_ADDRESS,
                deadline,
                amount,
                min_amount_out
            )]
        )

        unwrap_data = self.swap_contract.encodeABI(
            fn_name="unwrapWETH9",
            args=[
                0,
                self.address
            ]

        )

        contract_txn = await self.swap_contract.functions.multicall(
            [transaction_data, unwrap_data]
        ).build_transaction(tx_data)

        return contract_txn
    
    async def swap(
            self,
            sell_token: str,
            buy_token: str,
            slippage: float,
            amount
    ):
        buy_token_decimals, sell_token_decimals = determine_decimals(buy_token, sell_token, coin_data)

        amount_parsed = get_amount(
            sell_token,
            amount,
            sell_token_decimals,
        )

        LOGGER.info(
            f"[{self.id}][{self.pubkey}] Swap on Maverick – {sell_token} -> {buy_token} |Sell {amount} {sell_token}"
        )

        pool_address = self.get_pool(sell_token, buy_token)

        if pool_address != ZERO_ADDRESS:

            if sell_token == "ETH":
                contract_txn = await self.swap_to_token(sell_token, buy_token, amount_parsed, slippage)
            elif buy_token == "ETH":
                contract_txn = await self.swap_to_eth(sell_token, buy_token, amount_parsed, slippage)
            else:
                pool_address = await self.get_pool(sell_token, buy_token)
                contract_txn = await self.swap_tokenA_to_tokenB(sell_token, buy_token, amount_parsed, slippage, pool_address)

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
    maverick_instance = Maverick(privkey)
    maverick_instance.swap('ETH','USDC',.01,0.001)

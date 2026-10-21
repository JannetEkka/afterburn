require("@nomicfoundation/hardhat-ethers");
require("@nomicfoundation/hardhat-chai-matchers");

const key = process.env.AFTERBURN_KEY;

module.exports = {
  solidity: { version: "0.8.24", settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "cancun" } },
  networks: {
    monadTestnet: { url: "https://testnet-rpc.monad.xyz", chainId: 10143, accounts: key ? [key] : [] },
  },
};

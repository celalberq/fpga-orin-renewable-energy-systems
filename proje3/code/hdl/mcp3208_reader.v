`timescale 1ns / 1ps

module mcp3208_reader #(
    parameter integer CLK_HZ = 100000000,
    parameter integer SPI_HZ = 1000000
) (
    input wire clk,
    input wire start,
    input wire [2:0] channel,
    input wire spi_miso,
    output reg spi_cs_n,
    output reg spi_sclk,
    output wire spi_mosi,
    output reg busy,
    output reg done,
    output reg [11:0] sample_data
);

    localparam integer HALF_PERIOD_CLKS = (CLK_HZ / (SPI_HZ * 2));
    localparam integer DIV_LIMIT = (HALF_PERIOD_CLKS < 1) ? 1 : HALF_PERIOD_CLKS;

    reg [31:0] div_count = 32'd0;
    reg [4:0] bit_count = 5'd0;
    reg [23:0] tx_shift = 24'd0;
    reg [23:0] rx_shift = 24'd0;

    assign spi_mosi = tx_shift[23];

    always @(posedge clk) begin
        done <= 1'b0;

        if (!busy) begin
            spi_cs_n <= 1'b1;
            spi_sclk <= 1'b0;
            div_count <= 32'd0;
            bit_count <= 5'd0;

            if (start) begin
                busy <= 1'b1;
                spi_cs_n <= 1'b0;
                spi_sclk <= 1'b0;
                div_count <= 32'd0;
                bit_count <= 5'd0;
                rx_shift <= 24'd0;
                tx_shift <= {5'b00000, 2'b11, channel[2], channel[1:0], 14'd0};
            end
        end else if (div_count == DIV_LIMIT - 1) begin
            div_count <= 32'd0;

            if (!spi_sclk) begin
                spi_sclk <= 1'b1;
                rx_shift <= {rx_shift[22:0], spi_miso};
            end else begin
                spi_sclk <= 1'b0;
                tx_shift <= {tx_shift[22:0], 1'b0};

                if (bit_count == 5'd23) begin
                    busy <= 1'b0;
                    spi_cs_n <= 1'b1;
                    done <= 1'b1;
                    sample_data <= rx_shift[11:0];
                end else begin
                    bit_count <= bit_count + 1'b1;
                end
            end
        end else begin
            div_count <= div_count + 1'b1;
        end
    end

    initial begin
        spi_cs_n = 1'b1;
        spi_sclk = 1'b0;
        busy = 1'b0;
        done = 1'b0;
        sample_data = 12'd0;
    end

endmodule

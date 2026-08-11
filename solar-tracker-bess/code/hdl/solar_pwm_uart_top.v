`timescale 1ns / 1ps

module solar_pwm_uart_top #(
    parameter integer CLK_HZ = 100000000,
    parameter integer BAUD = 115200,
    parameter integer SEND_INTERVAL_CLKS = 100000000
) (
    input wire clk,
    input wire [7:0] sw,
    input wire uart_tx_in,
    output wire [7:0] led,
    output wire uart_rx_out
);

    localparam integer MSG_LEN = 38;

    wire [7:0] duty = sw;
    wire [7:0] fake_voltage = 8'h80 + {2'b00, sw[7:2]};
    wire [7:0] fake_current = 8'h10 + {3'b000, sw[7:3]};
    wire [7:0] fake_power = {1'b0, duty[7:1]};
    wire pwm_out;
    wire uart_busy;
    wire uart_done;

    reg [31:0] interval_count = 32'd0;
    reg [7:0] msg_index = 8'd0;
    reg [7:0] tx_data = 8'd0;
    reg tx_start = 1'b0;
    reg sending = 1'b1;
    reg heartbeat = 1'b0;

    assign led[0] = pwm_out;
    assign led[1] = heartbeat;
    assign led[2] = uart_busy;
    assign led[7:3] = sw[7:3];

    pwm_generator #(
        .WIDTH(8)
    ) pwm_inst (
        .clk(clk),
        .duty(duty),
        .pwm_out(pwm_out)
    );

    uart_tx #(
        .CLK_HZ(CLK_HZ),
        .BAUD(BAUD)
    ) uart_tx_inst (
        .clk(clk),
        .reset(1'b0),
        .tx_start(tx_start),
        .tx_data(tx_data),
        .tx_line(uart_rx_out),
        .busy(uart_busy),
        .done(uart_done)
    );

    function [7:0] hex_char;
        input [3:0] nibble;
        begin
            case (nibble)
                4'h0: hex_char = "0";
                4'h1: hex_char = "1";
                4'h2: hex_char = "2";
                4'h3: hex_char = "3";
                4'h4: hex_char = "4";
                4'h5: hex_char = "5";
                4'h6: hex_char = "6";
                4'h7: hex_char = "7";
                4'h8: hex_char = "8";
                4'h9: hex_char = "9";
                4'ha: hex_char = "A";
                4'hb: hex_char = "B";
                4'hc: hex_char = "C";
                4'hd: hex_char = "D";
                4'he: hex_char = "E";
                4'hf: hex_char = "F";
                default: hex_char = "?";
            endcase
        end
    endfunction

    function [7:0] message_char;
        input [7:0] index;
        begin
            case (index)
                8'd0:  message_char = "p";
                8'd1:  message_char = "3";
                8'd2:  message_char = ",";
                8'd3:  message_char = "d";
                8'd4:  message_char = "u";
                8'd5:  message_char = "t";
                8'd6:  message_char = "y";
                8'd7:  message_char = "=";
                8'd8:  message_char = "0";
                8'd9:  message_char = "x";
                8'd10: message_char = hex_char(duty[7:4]);
                8'd11: message_char = hex_char(duty[3:0]);
                8'd12: message_char = ",";
                8'd13: message_char = "v";
                8'd14: message_char = "=";
                8'd15: message_char = "0";
                8'd16: message_char = "x";
                8'd17: message_char = hex_char(fake_voltage[7:4]);
                8'd18: message_char = hex_char(fake_voltage[3:0]);
                8'd19: message_char = ",";
                8'd20: message_char = "i";
                8'd21: message_char = "=";
                8'd22: message_char = "0";
                8'd23: message_char = "x";
                8'd24: message_char = hex_char(fake_current[7:4]);
                8'd25: message_char = hex_char(fake_current[3:0]);
                8'd26: message_char = ",";
                8'd27: message_char = "p";
                8'd28: message_char = "=";
                8'd29: message_char = "0";
                8'd30: message_char = "x";
                8'd31: message_char = hex_char(fake_power[7:4]);
                8'd32: message_char = hex_char(fake_power[3:0]);
                8'd33: message_char = ",";
                8'd34: message_char = "o";
                8'd35: message_char = "k";
                8'd36: message_char = 8'h0d;
                8'd37: message_char = 8'h0a;
                default: message_char = 8'h20;
            endcase
        end
    endfunction

    always @(posedge clk) begin
        tx_start <= 1'b0;

        if (!sending) begin
            if (interval_count == SEND_INTERVAL_CLKS - 1) begin
                interval_count <= 32'd0;
                msg_index <= 8'd0;
                sending <= 1'b1;
                heartbeat <= ~heartbeat;
            end else begin
                interval_count <= interval_count + 1;
            end
        end else if (!uart_busy && !tx_start) begin
            if (msg_index < MSG_LEN) begin
                tx_data <= message_char(msg_index);
                tx_start <= 1'b1;
                msg_index <= msg_index + 1;
            end else begin
                sending <= 1'b0;
            end
        end
    end

    wire unused_uart_tx = uart_tx_in;
    wire unused_uart_done = uart_done;

endmodule
